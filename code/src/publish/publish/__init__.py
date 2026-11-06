from __future__ import annotations

import argparse
from json import dumps
from random import choice

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import ValidationError

from .commands import run_og_tiles, run_posters, run_similar, run_web_posters
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

    s3 = boto3.client("s3", Config=Config(max_pool_connections=settings.MAX_S3_THREADS))

    # first signal, job actually launched and nothing else; enforce idempotency via
    # cached property retrievals first, which need to be validated at launch

    print(f"Publish job triggered for {settings.SET} ({settings.RUN})")

    admin.update_progress(
        Status.IN_PROGRESS,
        "publish job launched",
    )

    # Setup directories, copy down source images, and list manifest (could check size too)

    mkdirs("images", "similar", "posters", "og")

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

    image_ids = list_image_ids()

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
            Key=f"drafts/{settings.POST_NAME}.json",
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
                "key": f"drafts/{settings.POST_NAME}.json",
            },
        )
    except ClientError as e:
        if e.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            print(
                "A manifest file for this post draft already exists at "
                f"s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}.json "
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
            "embeddings.npy",
            "similiar",
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

    try:
        run_og_tiles(
            settings.SET_NAME,
            settings.RAW_PREFIX,
            "images",
            "og",
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

    try:
        run_posters(
            settings.POSTER_SIZES,
            settings.POST_TITLE,
            "images",
            "posters",
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

    try:
        run_web_posters(
            "posters",
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
        "prepared publishable content",
    )

    # Upload additional content to S3, actual site source
    try:
        do_uploads(settings, s3)
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
    )

    # TODO: submit a PR with this data organized if we can clone main branch?

    admin.update_progress(
        Status.COMPLETED,
        "all content prepared and uploaded to S3",
    )


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--batch-run-id", required=True)
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
