"""Ad-hoc smoke test for GithubPublisher.create_draft_pr."""

import json
import os

import boto3

from publish.publish.github import GithubPublisher, draft_files
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
draft_manifest = json.loads(spec["Body"].read())

og_filename = f"og/{settings.SET_NAME}.jpg"
os.makedirs("og", exist_ok=True)
s3.download_file(
    Bucket=settings.SITE_BUCKET,
    Key=f"assets/og/{settings.SET_NAME}.jpg",
    Filename=og_filename,
)

try:
    publisher = GithubPublisher(
        app_id=settings.GITHUB_APP_ID,
        client_id=settings.GITHUB_APP_CLIENT_ID,
        installation_id=settings.GITHUB_APP_INSTALLATION_ID,
        private_key=settings.GITHUB_APP_PRIVATE_KEY,
        owner=settings.GITHUB_REPO_OWNER,
        repo=settings.GITHUB_REPO_NAME,
    )

    pr_url = publisher.create_draft_pr(
        files=draft_files(settings, draft_manifest),
        title=f"Publish draft: {settings.POST_NAME}",
        body=(
            f"Publish draft for set {settings.SET_NAME} (post {settings.POST_NAME}). "
            f"Draft manifest: s3://{settings.SITE_BUCKET}/drafts/{settings.POST_NAME}/spec.json"
        ),
        branch=f"draft/{settings.POST_NAME}",
    )

    print(f"Created draft PR: {pr_url}")

except Exception as e:
    print(f"Failed to create PR: {e.__class__.__name__} {e}")

finally:
    os.remove(og_filename)
