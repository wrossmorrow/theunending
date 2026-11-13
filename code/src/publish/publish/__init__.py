from __future__ import annotations

import argparse
from json import dumps
from pathlib import Path
from random import choice
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from PIL import Image
from pydantic import ValidationError

from ..progress import AdminAPI, Status
from .commands import run_og_tiles, run_posters, run_similar, run_web_posters
from .github import github_publish
from .manifest import DraftManifest, SetSpec
from .post import post_draft
from .settings import PublishSettings
from .utils import do_uploads, get_source_content, list_image_ids


def _just_publish_pr(
    s3: S3Client,
    settings: PublishSettings,
    admin: AdminAPI,
) -> int:

    # get the spec draft manifest instead of making it here
    draft_manifest: DraftManifest
    thumb_id: str
    s3.download_file(
        Bucket=settings.SITE_BUCKET,
        Key=f"drafts/{settings.POST_NAME}/spec.json",
        Filename="spec.json",
    )
    with open("spec.json", "r") as f:
        draft_manifest = DraftManifest.model_validate_json(f.read())
        thumb_id = draft_manifest.set_spec.thumb

    # get
    #
    #   * s3://{settings.SITE_BUCKET}/assets/og/{settings.SET_NAME}.jpg
    #       -> og/{settings.SET_NAME}.jpg
    #   * s3://{settings.SITE_BUCKET}/assets/img/index-thumbs/{draft_manifest.set_spec.thumb}.webp
    #       -> {draft_manifest.set_spec.thumb}.webp
    #
    # locally
    og_image_path = f"{settings.SET_NAME}.jpg"
    it_image_path = f"{thumb_id}.webp"
    s3.download_file(
        Bucket=settings.SITE_BUCKET,
        Key=f"assets/og/{settings.SET_NAME}.jpg",
        Filename=og_image_path,
    )
    s3.download_file(
        Bucket=settings.SITE_BUCKET,
        Key=f"assets/img/index-thumbs/{draft_manifest.set_spec.thumb}.webp",
        Filename=it_image_path,
    )

    try:
        draft_pr_url = github_publish(
            settings=settings,
            manifest=draft_manifest,
            og_image_path=og_image_path,
            it_image_path=it_image_path,
        )
        admin.update_progress(
            Status.COMPLETED,
            "created draft pull request",
            details={"draft_pr_url": draft_pr_url},
        )
        return 0
    except Exception as e:  # noqa: BLE001
        admin.update_progress(
            Status.FAILED,
            "failed to create draft pull request",
            details={"error": str(e), "error_class": e.__class__.__name__},
        )
        print(f"Failed to create draft PR: {e.__class__.__name__} {e}")

    return 1


def handle(args: argparse.Namespace) -> None:

    settings = PublishSettings(RUN_ID=args.run_id)

    admin = AdminAPI(
        url=settings.ADMIN_API_URL,
        auth_secret=settings.ADMIN_API_TOKEN,
        auth_secret_type="Bearer",
        admin_run_id=settings.RUN_ID,
    )

    s3 = boto3.client("s3", config=Config(max_pool_connections=settings.MAX_S3_THREADS))

    # first signal, job actually launched and nothing else; enforce idempotency via
    # cached property retrievals first, which need to be validated at launch

    print(f"Publish job triggered for {settings.SET} ({settings.RUN})")

    admin.update_progress(
        Status.IN_PROGRESS,
        "publish job launched",
    )

    # special handling if we just need to make the PR

    if args.github_pr_only:
        raise SystemExit(_just_publish_pr(s3, settings, admin))

    # Setup directories, copy down source images, and list manifest (could check size too)

    for dir in (
        settings.IMAGES_DIR,
        settings.SIMILAR_DIR,
        settings.OG_TILE_DIR,
        settings.POSTERS_DIR,
    ):
        Path(f"./{dir}").mkdir(parents=True, exist_ok=True)

    print(f"Directories: {[d for d in Path('.').iterdir()]}")

    # process starts with getting all the source content

    try:
        get_source_content(
            settings=settings,
            s3=s3,
            bucket=settings.RAW_BUCKET,
            prefix=settings.RAW_PREFIX,
        )
    except ValidationError as e:
        admin.update_progress(
            Status.FAILED,
            "settings configuration failure when retrieving source",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "an unexpected error occurred retrieving source content",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    image_ids = list_image_ids(settings.IMAGES_DIR)

    admin.update_progress(
        Status.IN_PROGRESS,
        "cloned content for publish work",
        details={
            "bucket": settings.RAW_BUCKET,
            "prefix": settings.RAW_PREFIX,
            "count": len(image_ids),
        },
    )

    # Create site draft content, the post draft, the id list, the sets data, the posters json
    # Finalize with one manifest JSON and upload to S3 for something else to work on as a draft
    # First so we can gate based on errors in overwriting
    post = post_draft(
        title=settings.POST_TITLE,
        subtitle=settings.PROMPT,
        date=settings.POST_DATE,
        set=settings.SET_NAME,
        model=settings.MODEL_ID,
        extra_details=args.extra_details,
    )
    draft_manifest = DraftManifest(
        set=settings.SET_NAME,
        post_name=settings.POST_NAME,
        post_draft=post,
        image_manifest=image_ids,
        set_spec=SetSpec(
            thumb=choice(image_ids),
            **settings.SET_SPEC,
        ),
        posters_spec=settings.POSTERS_SPEC,
    )

    try:
        s3.put_object(
            Bucket=settings.SITE_BUCKET,
            Key=f"drafts/{settings.POST_NAME}/spec.json",
            Body=draft_manifest.model_dump_json().encode("utf-8"),
            ContentType="application/json",
            IfNoneMatch="*",
        )
        # TODO: we don't really want errors here caught in the same block
        # but as of commenting update_progress never raises
        admin.update_progress(
            Status.IN_PROGRESS,
            "posted draft manifest to S3",
            details={
                "bucket": settings.SITE_BUCKET,
                "key": f"drafts/{settings.POST_NAME}/spec.json",
            },
        )
    except ClientError as e:
        if e.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            print(
                "A manifest file for this post draft already exists at "
                f"s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}/spec.json "
                "which must be reviewed before clobbering with a new draft"
            )
            admin.update_progress(
                Status.FAILED,
                "idempotency failure in draft manifest",
            )
        else:
            admin.update_progress(
                Status.FAILED,
                "s3 client error",
                details={
                    "error_code": e.response["Error"]["Code"],
                },
            )
        raise
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "an unexpected error occurred posting draft manifest",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    # Create additional content needed (similar JSONs, OG tiles, posters)
    # TODO: images we get are "full" size, create thumbs and "mid" size

    try:
        run_similar(
            input="embeddings.npy",
            output=settings.SIMILAR_DIR,
        )
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to create similarity mappings",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared similar image manifests",
    )

    try:
        run_og_tiles(
            set=settings.SET_NAME,
            prefix=settings.RAW_PREFIX,
            source=settings.IMAGES_DIR,
            output=settings.OG_TILE_DIR,
        )
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to create OG tile image(s)",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared og tile(s)",
    )

    try:
        thumb_id = draft_manifest.set_spec.thumb
        im = Image.open(f"{settings.IMAGES_DIR}/{thumb_id}.png")
        im = im.convert("RGB")
        im.thumbnail((640, 640), Image.LANCZOS)
        with open(f"{thumb_id}.webp", "wb") as f:
            im.save(f, "WEBP", quality=80, method=6)

    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to create index thumb",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared index thumb",
    )

    try:
        run_posters(
            sizes=settings.POSTER_SIZES,
            title=settings.POST_TITLE,
            source=settings.IMAGES_DIR,
            output=settings.POSTERS_DIR,
        )
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to create full size posters",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared full posters",
    )

    try:
        run_web_posters(
            sizes=settings.POSTER_SIZES,
            source=settings.POSTERS_DIR,
        )
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to create similarity mappings",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared web posters",
    )

    # Upload additional content to S3, actual site source
    try:
        report = do_uploads(settings, s3, draft_manifest.set_spec.thumb)
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to upload publishable content",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "uploaded publishable content",
        details={
            "report_key": f"drafts/{settings.POST_NAME}/report.json",
        },
    )

    # Upload the report of upload counts collected during the publish uploads

    try:
        s3.put_object(
            Bucket=settings.SITE_BUCKET,
            Key=f"drafts/{settings.POST_NAME}/report.json",
            Body=dumps(report, default=str).encode("utf-8"),
            ContentType="application/json",
            IfNoneMatch="*",
        )
    except ClientError as e:
        admin.update_progress(
            Status.FAILED,
            "s3 client error",
            details={
                "error_code": e.response["Error"]["Code"],
            },
        )
        raise
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "an unexpected error occurred posting report",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            },
        )
        raise

    try:
        draft_pr_url = github_publish(settings=settings, manifest=draft_manifest)
        admin.update_progress(
            Status.IN_PROGRESS,
            "created draft pull request",
            details={"draft_pr_url": draft_pr_url},
        )
    except Exception as e:  # noqa: BLE001
        admin.update_progress(
            Status.IN_PROGRESS,
            "failed to create draft pull request",
            details={"error": str(e), "error_class": e.__class__.__name__},
        )
        print(f"Failed to create draft PR: {e.__class__.__name__} {e}")

    admin.update_progress(
        Status.COMPLETED,
        "all content prepared and uploaded to S3",
        details={
            "spec_s3_location": f"s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}/spec.json",
            "report_s3_location": f"s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}/report.json",
        },
    )


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--extra-details", default=None)
    parser.add_argument("--github-pr-only", action="store_true", default=False)
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
