"""S3 helpers for the Unending Admin API."""

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from api.settings import settings


def create_presigned_url(bucket: str, key: str, expires_in: int) -> str:
    """Create a presigned S3 GET URL for the given object key."""
    client = boto3.client(
        "s3",
        region_name=settings.aws_region_name,
        config=Config(signature_version="s3v4"),
    )
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
