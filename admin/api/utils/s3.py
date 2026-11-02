"""S3 helpers for the Unending Admin API."""

import boto3  # type: ignore[import-untyped]

DEFAULT_EXPIRES_SECONDS = 3600


def create_presigned_url(
    bucket: str, key: str, expires_in: int = DEFAULT_EXPIRES_SECONDS
) -> str:
    """Create a presigned S3 GET URL for the given object key."""
    client = boto3.client("s3")
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def find_object_key(bucket: str, prefix: str, suffix: str = ".png") -> str | None:
    """Find the first object key under a prefix ending with a suffix."""
    client = boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if key.startswith(prefix) and key[len(prefix) :].lower().endswith(suffix):
                return key
    return None
