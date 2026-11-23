"""Ad-hoc smoke test for GithubPublisher.create_draft_pr."""

import json
import os

import boto3

from publish.publish.github import github_publish
from publish.publish.manifest import DraftManifest
from publish.publish.settings import PublishSettings

with open(os.environ["GITHUB_APP_PRIVATE_KEY_FILE"], "r") as f:
    settings = PublishSettings(
        GITHUB_APP_PRIVATE_KEY=f.read(),
        REQUIRE_PENDING=False,
    )

s3 = boto3.client("s3")

spec = s3.get_object(
    Bucket=settings.SITE_BUCKET,
    Key=f"drafts/{settings.POST_NAME}/spec.json",
)
draft_manifest = DraftManifest.model_validate(json.loads(spec["Body"].read()))

og_filename = f"og/{settings.SET_NAME}.jpg"
thumb_filename = f"{draft_manifest.set_spec.thumb}.webp"
os.makedirs("og", exist_ok=True)
s3.download_file(
    Bucket=settings.SITE_BUCKET,
    Key=f"{settings.SITE_OG_IMAGE_PREFIX}/{settings.SET_NAME}.jpg",
    Filename=og_filename,
)
s3.download_file(
    Bucket=settings.SITE_BUCKET,
    Key=f"{settings.SITE_INDEX_THUMBS_PREFIX}/{draft_manifest.set_spec.thumb}.webp",
    Filename=thumb_filename,
)

try:
    pr_url = github_publish(
        settings=settings,
        manifest=draft_manifest,
        og_image_path=og_filename,
        it_image_path=thumb_filename,
    )

    print(f"Created draft PR: {pr_url}")

except Exception as e:  # noqa: BLE001
    print(f"Failed to create PR: {e.__class__.__name__} {e}")

finally:
    os.remove(og_filename)
    os.remove(thumb_filename)
