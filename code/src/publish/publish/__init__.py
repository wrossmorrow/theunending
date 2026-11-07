from __future__ import annotations

import argparse
from json import dumps
from pathlib import Path
from random import choice

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import ValidationError

from .commands import run_og_tiles, run_posters, run_similar, run_web_posters
from .github import GithubPublisher, draft_files
from .post import post_draft
from .settings import PublishSettings
from .utils import do_uploads, get_source_content, list_image_ids, mkdirs
from ..progress import AdminAPI, Status


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

    # Setup directories, copy down source images, and list manifest (could check size too)

    for dir in (
        settings.IMAGES_DIR,
        settings.SIMILAR_DIR,
        settings.OG_TILE_DIR,
        settings.POSTERS_DIR,
    ):
        Path(f"./{dir}").mkdir(parents=True, exist_ok=True)

    print(f"Directories: {[d for d in Path('.').iterdir()]}")

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
            }
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
    )
    draft_manifest = {
        "set": settings.SET_NAME,
        "post_name": settings.POST_NAME,
        "post_draft": post,
        "image_manifest": image_ids,
        "set_spec": {
            "thumb": choice(image_ids),
            **settings.SET_SPEC,
        },
        "posters_spec": settings.POSTERS_SPEC,
    }

    try:
        s3.put_object(
            Bucket=settings.SITE_BUCKET,
            Key=f"drafts/{settings.POST_NAME}/spec.json",
            Body=dumps(draft_manifest, default=str).encode("utf-8"),
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
                }
            )
        raise
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "an unexpected error occurred posting draft manifest",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            }
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
            }
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
            }
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared og tile(s)",
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
            }
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
            }
        )
        raise

    admin.update_progress(
        Status.IN_PROGRESS,
        "prepared web posters",
    )

    # Upload additional content to S3, actual site source
    try:
        report = do_uploads(settings, s3)
    except Exception as e:
        admin.update_progress(
            Status.FAILED,
            "failed to upload publishable content",
            details={
                "error": str(e),
                "error_class": e.__class__.__name__,
            }
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
        github_publisher = GithubPublisher(
            app_id=settings.GITHUB_APP_ID,
            client_id=settings.GITHUB_APP_CLIENT_ID,
            installation_id=settings.GITHUB_APP_INSTALLATION_ID,
            private_key=settings.GITHUB_APP_PRIVATE_KEY,
            owner=settings.GITHUB_REPO_OWNER,
            repo=settings.GITHUB_REPO_NAME,
        )
        draft_pr_url = github_publisher.create_draft_pr(
            files=draft_files(settings, draft_manifest),
            title=f"Publish draft: {settings.POST_NAME}",
            body=(
                f"Publish draft for set {settings.SET_NAME} (post {settings.POST_NAME}). "
                f"Draft manifest: s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}/spec.json"
            ),
            branch=f"draft/{settings.POST_NAME}",
        )
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
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
