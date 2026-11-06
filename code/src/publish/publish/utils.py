from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
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
    settings: PublishSettings,
    s3: S3Client,
    bucket: str,
    prefix: str,
    image_ext: str = ".png",
    emb_file: str = "embeddings.npy",
) -> None:
    """get content locally; everything stems from images and embeddings"""
    cp_from_s3(s3, bucket, prefix + "/", settings.IMAGES_DIR, ext=image_ext, workers=settings.MAX_S3_THREADS)
    cp_from_s3(s3, bucket, f"{prefix}/{emb_file}", emb_file)
    cp_from_s3(s3, bucket, f"{prefix}/{emb_file}.json", f"{emb_file}.json")


def list_image_ids(
    source: str,
    ext: str = ".png",
) -> list[str]:
    return [fn.strip(f"{source}/").strip(ext) for fn in glob(f"{source}/*{ext}")]


def put_file_no_overwrite(
    s3: S3Client,
    filename: str,
    bucket: str,
    key: str,
    content_type: str,
) -> None:
    with open(filename, "rb") as f:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=f,
            ContentType=content_type,
            IfNoneMatch="*",
        )


def batch_put_file_no_overwrite(
    s3: S3Client,
    pattern: str,
    bucket: str,
    prefix: str,
    content_type: str,
    max_workers: int,
) -> list[tuple[str, Exception]]:
    failed = []
    with ThreadPoolExecutor(max_workers=max_workers) as tpe:
        futures = {
            tpe.submit(
                put_file_no_overwrite,
                s3,
                path,
                bucket,
                f"{prefix}/{Path(path).name}",
                content_type,
            ): str(path)
            for path in glob(pattern)
        }
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                failed.append((futures[f], e))

    return failed


def do_uploads(
    settings: PublishSettings,
    s3: S3Client,
) -> None:

    # images/*.png -> SITE_BUCKET, assets/img/POST_NAME/
    failed = batch_put_file_no_overwrite(
        s3=s3,
        pattern=f"{settings.IMAGES_DIR}/*.png",
        bucket=settings.SITE_BUCKET,
        prefix=settings.SITE_IMG_ASSETS_PREFIX,
        content_type="image/png",
        max_workers=settings.MAX_S3_THREADS,
    )

    # images/*.json -> SITE_BUCKET, assets/img/POST_NAME/
    failed = batch_put_file_no_overwrite(
        s3=s3,
        pattern=f"{settings.SIMILAR_DIR}/*.json",
        bucket=settings.SITE_BUCKET,
        prefix=settings.SITE_IMG_ASSETS_PREFIX,
        content_type="application/json",
        max_workers=settings.MAX_S3_THREADS,
    )

    # og/SET_NAME.jpg -> SITE_BUCKET, assets/og/SET_NAME.jpg
    put_file_no_overwrite(
        s3=s3,
        filename=f"{settings.OG_TILE_DIR}/{settings.SET_NAME}.jpg",
        bucket=settings.SITE_BUCKET,
        key=f"{settings.SITE_OG_IMAGE_PREFIX}/{settings.SET_NAME}.jpg",
        content_type="image/jpeg",
    )

    # posters/*.png -> SITE_BUCKET, assets/img/posters/raw/POST_NAME/* (TODO: block public access?)
    for path in glob(f"{settings.POSTERS_DIR}/*.png"):
        put_file_no_overwrite(
            s3=s3,
            filename=path,
            bucket=settings.SITE_BUCKET,
            key=f"{settings.SITE_POSTER_RAW_PREFIX}/{Path(path).name}",
            content_type="image/png",
        )

    # posters/previews/*.webp -> SITE_BUCKET, assets/img/posters/previews/POST_NAME/*

    for path in glob(f"{settings.POSTERS_DIR}/previews/*.webp"):
        put_file_no_overwrite(
            s3=s3,
            filename=path,
            bucket=settings.SITE_BUCKET,
            key=f"{settings.SITE_POSTER_PREVIEW_PREFIX}/{Path(path).name}",
            content_type="image/webp",
        )

    # posters/thumbs/*.webp -> SITE_BUCKET, assets/img/posters/thumbs/POST_NAME/*

    for path in glob(f"{settings.POSTERS_DIR}/thumbs/*.webp"):
        put_file_no_overwrite(
            s3=s3,
            flename=path,
            bucket=settings.SITE_BUCKET,
            key=f"{settings.SITE_POSTER_THUMBS_PREFIX}/{Path(path).name}",
            content_type="image/webp",
        )
