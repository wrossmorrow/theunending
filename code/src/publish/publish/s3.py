from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def ls_s3(
    s3: S3Client, bucket: str, prefix: str, ext: str | None = ".png"
) -> list[str]:

    results: list[str] = []

    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if ext is not None and not key.endswith(ext):
                continue

            key[len(prefix) :]
            key = key[-len(ext) :]
            if not key:
                continue

            results.append(key)

    return results


def cp_from_s3(
    s3: S3Client,
    bucket: str,
    prefix: str,
    local: Path,
    ext: str | None = None,
    workers: int = 32,
) -> None:

    if isinstance(local, str):
        cp_from_s3(s3, bucket, prefix, Path(local), ext=ext)
        return

    if not prefix.endswith("/"):
        local.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(bucket, prefix, str(local))
        return

    paginator = s3.get_paginator("list_objects_v2")

    def _fetch(key: str, target: str) -> None:
        s3.download_file(bucket, key, target)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]

                if ext is not None and not key.endswith(ext):
                    continue

                rel_path = key[len(prefix) :]
                if not rel_path:
                    continue

                target = local / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                pool.submit(_fetch, key, str(target))
                # s3.download_file(bucket, key, str(target))
