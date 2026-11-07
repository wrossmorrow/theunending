from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from .s3 import cp_from_s3
from .settings import PublishSettings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


class PreconditionFailedError(Exception):
    """Raised when an S3 conditional write (IfNoneMatch) is rejected as conflicting."""

    def __init__(self, bucket: str, key: str) -> None:
        super().__init__(f"Object already exists at s3://{bucket}/{key}")
        self.bucket = bucket
        self.key = key


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


def list_image_ids(source: str, ext: str = ".png") -> list[str]:
    return [Path(fn).stem for fn in glob(f"{source}/*{ext}")]


def put_file_no_overwrite(
    s3: S3Client,
    filename: str,
    bucket: str,
    key: str,
    content_type: str,
) -> None:
    try:
        with open(filename, "rb") as f:
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=f,
                ContentType=content_type,
                IfNoneMatch="*",
            )
    except ClientError as e:
        if e.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            raise PreconditionFailedError(bucket=bucket, key=key) from e
        raise


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
) -> dict:
    """
    Upload all publishable content to the site bucket, collecting counts of
    files uploaded from each source to each bucket/prefix along the way.

    Raises a ValueError if any file failed to upload.
    """

    failed: list[tuple[str, Exception]] = []

    report: dict = {}

    # images/*.png -> SITE_BUCKET, assets/img/POST_NAME/
    failed_files = batch_put_file_no_overwrite(
        s3=s3,
        pattern=f"{settings.IMAGES_DIR}/*.png",
        bucket=settings.SITE_BUCKET,
        prefix=settings.SITE_IMG_ASSETS_PREFIX,
        content_type="image/png",
        max_workers=settings.MAX_S3_THREADS,
    )
    failed.extend(failed_files)
    report[f"{settings.IMAGES_DIR}/*.png"] = {
        "bucket": settings.SITE_BUCKET,
        "prefix": settings.SITE_IMG_ASSETS_PREFIX,
        "uploaded": len(glob(f"{settings.IMAGES_DIR}/*.png")) - len(failed_files),
    }

    # images/*.json -> SITE_BUCKET, assets/img/POST_NAME/
    failed_files = batch_put_file_no_overwrite(
        s3=s3,
        pattern=f"{settings.SIMILAR_DIR}/*.json",
        bucket=settings.SITE_BUCKET,
        prefix=settings.SITE_IMG_ASSETS_PREFIX,
        content_type="application/json",
        max_workers=settings.MAX_S3_THREADS,
    )
    failed.extend(failed_files)
    report[f"{settings.SIMILAR_DIR}/*.json"] = {
        "bucket": settings.SITE_BUCKET,
        "prefix": settings.SITE_IMG_ASSETS_PREFIX,
        "uploaded": len(glob(f"{settings.SIMILAR_DIR}/*.json")) - len(failed_files),
    }

    # og/SET_NAME.jpg -> SITE_BUCKET, assets/og/SET_NAME.jpg
    put_file_no_overwrite(
        s3=s3,
        filename=f"{settings.OG_TILE_DIR}/{settings.SET_NAME}.jpg",
        bucket=settings.SITE_BUCKET,
        key=f"{settings.SITE_OG_IMAGE_PREFIX}/{settings.SET_NAME}.jpg",
        content_type="image/jpeg",
    )
    report[f"og/{settings.SET_NAME}.jpg"] = {
        "bucket": settings.SITE_BUCKET,
        "prefix": settings.SITE_OG_IMAGE_PREFIX,
        "uploaded": 1,
    }

    # posters/*.png -> SITE_BUCKET, assets/img/posters/raw/POST_NAME/* (TODO: block public access?)
    poster_files = glob(f"{settings.POSTERS_DIR}/*.png")
    for path in poster_files:
        put_file_no_overwrite(
            s3=s3,
            filename=path,
            bucket=settings.SITE_BUCKET,
            key=f"{settings.SITE_POSTER_RAW_PREFIX}/{Path(path).name}",
            content_type="image/png",
        )
    report[f"{settings.POSTERS_DIR}/*.png"] = {
        "bucket": settings.SITE_BUCKET,
        "prefix": settings.SITE_POSTER_RAW_PREFIX,
        "uploaded": len(poster_files),
    }

    # posters/previews/*.webp -> SITE_BUCKET, assets/img/posters/previews/POST_NAME/*

    preview_files = glob(f"{settings.POSTERS_DIR}/previews/*.webp")
    for path in preview_files:
        put_file_no_overwrite(
            s3=s3,
            filename=path,
            bucket=settings.SITE_BUCKET,
            key=f"{settings.SITE_POSTER_PREVIEW_PREFIX}/{Path(path).name}",
            content_type="image/webp",
        )
    report[f"{settings.POSTERS_DIR}/previews/*.webp"] = {
        "bucket": settings.SITE_BUCKET,
        "prefix": settings.SITE_POSTER_PREVIEW_PREFIX,
        "uploaded": len(preview_files),
    }

    # posters/thumbs/*.webp -> SITE_BUCKET, assets/img/posters/thumbs/POST_NAME/*

    thumb_files = glob(f"{settings.POSTERS_DIR}/thumbs/*.webp")
    for path in thumb_files:
        put_file_no_overwrite(
            s3=s3,
            filename=path,
            bucket=settings.SITE_BUCKET,
            key=f"{settings.SITE_POSTER_THUMBS_PREFIX}/{Path(path).name}",
            content_type="image/webp",
        )
    report[f"{settings.POSTERS_DIR}/thumbs/*.webp"] = {
        "bucket": settings.SITE_BUCKET,
        "prefix": settings.SITE_POSTER_THUMBS_PREFIX,
        "uploaded": len(thumb_files),
    }

    if failed:
        for path, error in failed:
            print(f"Failed to upload {path}: {error.__class__.__name__} {error}")
        raise ValueError(f"Failed to upload publishable content: {len(failed)} file(s)")

    return report
