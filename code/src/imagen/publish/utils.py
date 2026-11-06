from __future__ import annotations

from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING

from .s3 import cp_from_s3
from .settings import PublishSettings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def mkdirs(*dirs: str) -> None:
    for dir in dirs:
        Path(dir).mkdir(parents=True, exist_ok=True)


def get_source_content(
    s3: S3Client,
    bucket: str,
    prefix: str,
    image_dir: str = "images",
    image_ext: str = ".png",
    emb_file: str = "embeddings.npy",
) -> None:
    """get content locally; everything stems from images and embeddings"""
    cp_from_s3(s3, bucket, prefix + "/", image_dir, ext=image_ext)
    cp_from_s3(s3, bucket, f"{prefix}/{emb_file}", emb_file)
    cp_from_s3(s3, bucket, f"{prefix}/{emb_file}.json", f"{emb_file}.json")


def list_image_ids(
    source: str = "images",
    ext: str = ".png",
) -> list[str]:
    return [fn.strip(f"{source}/").strip(ext) for fn in glob(f"{source}/*{ext}")]


def do_uploads(
    settings: PublishSettings,
    s3: S3Client,
) -> None:

    # images/*.png -> SITE_BUCKET, assets/img/POST_NAME/
    for path in glob("images/*.png"):
        fn = path.split("/")[-1]
        s3.upload_file(
            Filename=fn,
            Bucket=settings.SITE_BUCKET,
            Key=f"{settings.SITE_IMG_ASSETS_PREFIX}/{fn}",
        )

    # images/*.json -> SITE_BUCKET, assets/img/POST_NAME/
    for path in glob("similar/*.json"):
        fn = path.split("/")[-1]
        s3.upload_file(
            Filename=fn,
            Bucket=settings.SITE_BUCKET,
            Key=f"{settings.SITE_IMG_ASSETS_PREFIX}/{fn}",
        )

    # og/SET_NAME.jpg -> SITE_BUCKET, assets/og/SET_NAME.jpg
    s3.upload_file(
        Filename=f"og/{settings.SET_NAME}.jpg",
        Bucket=settings.SITE_BUCKET,
        Key=f"{settings.SITE_OG_IMAGE_PREFIX}/{settings.SET_NAME}.jpg",
    )

    # posters/*.png -> SITE_BUCKET, assets/img/posters/raw/POST_NAME/* (TODO: block public access?)
    for path in glob("posters/*.png"):
        fn = path.split("/")[-1]
        s3.upload_file(
            Filename=fn,
            Bucket=settings.SITE_BUCKET,
            Key=f"{settings.SITE_POSTER_RAW_PREFIX}/{fn}",
        )

    # posters/{previews,thumbs}/*.webp -> SITE_BUCKET, assets/img/posters/{previews,thumbs}/POST_NAME/*
    for path in glob("posters/previews/*.webp"):
        fn = path.split("/")[-1]
        s3.upload_file(
            Filename=fn,
            Bucket=settings.SITE_BUCKET,
            Key=f"{settings.SITE_POSTER_PREVIEW_PREFIX}/{fn}",
        )
    for path in glob("posters/thumbs/*.webp"):
        fn = path.split("/")[-1]
        s3.upload_file(
            Filename=fn,
            Bucket=settings.SITE_BUCKET,
            Key=f"{settings.SITE_POSTER_THUMBS_PREFIX}/{fn}",
        )
