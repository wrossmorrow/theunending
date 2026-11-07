"""Ad-hoc smoke test for GithubPublisher.create_draft_pr."""

import json

import boto3

from publish.publish.github import GithubPublisher, draft_files
from publish.publish.settings import PublishSettings

settings = PublishSettings(
    RUN_ID="12345678-1234-1234-1234-123456789012",
    ADMIN_API_TOKEN="dummy-admin-token",
    GITHUB_APP_ID="dummy-app-id",
    GITHUB_APP_CLIENT_ID="dummy-client-id",
    GITHUB_APP_INSTALLATION_ID="123456",
    GITHUB_APP_PRIVATE_KEY="dummy-private-key",
    GITHUB_REPO_OWNER="wrossmorrow",
    GITHUB_REPO_NAME="theunending",
)

s3 = boto3.client("s3")

spec = s3.get_object(
    Bucket=settings.SITE_BUCKET,
    Key=f"drafts/{settings.POST_NAME}/spec.json",
)
draft_manifest = json.loads(spec["Body"].read())

publisher = GithubPublisher(
    app_id="dummy-app-id",
    client_id="dummy-client-id",
    installation_id="123456",
    private_key="dummy-private-key",
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
