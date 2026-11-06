from __future__ import annotations

import argparse
from json import dumps
from random import choice

import boto3
from botocore.exceptions import ClientError

from .commands import run_og_tiles, run_posters, run_similar, run_web_posters
from .post import post_draft
from .settings import PublishSettings
from .utils import do_uploads, get_source_content, list_image_ids, mkdirs


def handle(args: argparse.Namespace) -> None:

    settings = PublishSettings(BATCH_RUN_ID=args.batch_run_id)

    s3 = boto3.client("s3")

    # Setup directories, copy down source images, and list manifest (could check size too)

    mkdirs("images", "similar", "posters", "og")
    get_source_content(
        s3=s3,
        bucket=settings.RAW_BUCKET,
        prefix=settings.RAW_PREFIX,
    )
    image_ids = list_image_ids()

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
            Body=dumps(draft_manifest).encode("utf-8"),
            ContentType="application/json",
            IfNoneMatch="*",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            print(
                "A manifest file for this post draft already exists at "
                f"s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}.json "
                "which must be reviewed before clobbering with a new draft"
            )
        raise

    # Create additional content needed (similar JSONs, OG tiles, posters)
    # TODO: images we get are "full" size, create thumbs and "mid" size

    run_similar(
        "embeddings.npy",
        "similiar",
    )
    run_og_tiles(
        settings.SET_NAME,
        settings.RAW_PREFIX,
        "images",
        "og",
    )
    run_posters(
        settings.POSTER_SIZES,
        settings.POST_TITLE,
        "images",
        "posters",
    )
    run_web_posters(
        "posters",
    )

    # Upload additional content to S3, actual site source
    do_uploads(settings, s3)

    # TODO: submit a PR with this data organized if we can clone main branch?


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
