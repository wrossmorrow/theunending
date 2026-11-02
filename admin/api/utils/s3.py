"""S3 helpers for the Unending Admin API."""

import boto3  # type: ignore[import-untyped]

DEFAULT_EXPIRES_SECONDS = 300


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
