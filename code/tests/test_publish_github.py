"""Tests for the publish task's draft PR creation and PR-only mode."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from publish.progress import Status
from publish.publish import _just_publish_pr, handle
from publish.publish.github import GithubPublisher, _draft_files
from publish.publish.manifest import DraftManifest

MANIFEST_JSON = json.dumps(
    {
        "set": "demo",
        "post_name": "2026-11-22-demo",
        "post_draft": "---\ntitle: Demo\n---\n",
        "image_manifest": ["thumb-1"],
        "set_spec": {
            "set": "demo",
            "base": "https://theunending.ai/assets/img/demo/",
            "manifest": "/assets/streams/demo.json",
            "meta": "/assets/img/demo/{id}.json",
            "thumb": "thumb-1",
        },
        "posters_spec": {},
    },
)


class FakeSettings:
    """Minimal publish settings stand-in; avoids live admin API access."""

    SITE_BUCKET = "theunending-ai-site-content-use1"
    POST_NAME = "2026-11-22-demo"
    SET_NAME = "demo"
    SITE_OG_IMAGE_PREFIX = "assets/og"
    SITE_INDEX_THUMBS_PREFIX = "assets/img/index-thumbs"
    SET = SimpleNamespace(slug="demo", post_date="2026-11-22")
    RUN = "2026-11-22-demo"
    RUN_ID = uuid4()
    MAX_S3_THREADS = 32
    POST_DATE = "2026-11-23"
    ADMIN_API_URL = (
        "http://localhost:8000/api/v0/runs/00000000-0000-0000-0000-000000000000/status"
    )


class FakeS3:
    """Fake S3 client that materializes downloaded objects as local files."""

    def __init__(self, spec_json: str = "{}") -> None:
        self.spec_json = spec_json
        self.downloads: list[tuple[str, str]] = []

    def download_file(self, *, Bucket: str, Key: str, Filename: str) -> None:
        """Record and materialize a single downloaded object."""
        self.downloads.append((Key, Filename))
        content = self.spec_json if Key.endswith("spec.json") else "content"
        Path(Filename).write_text(content)


class FakeAdminAPI:
    """Fake admin progress reporter recording status updates."""

    def __init__(self) -> None:
        self.calls: list[tuple[Status, str, dict | None]] = []

    def update_progress(
        self,
        status: Status,
        message: str,
        details: dict | None = None,
    ) -> None:
        """Record a status update."""
        self.calls.append((status, message, details))


class FakeGithubPublish:
    """Fake github_publish callable recording invocations."""

    def __init__(self, result: str = "https://github.com/owner/repo/pull/9") -> None:
        """Create a fake github_publish with an optional result."""
        self.result = result
        self.calls: list[dict] = []

    def __call__(self, **kwargs: dict) -> str:
        """Record and return a canned draft PR url."""
        self.calls.append(kwargs)
        return self.result


def _make_manifest() -> DraftManifest:
    """Build a validated draft manifest from the test fixture JSON."""
    return DraftManifest.model_validate_json(MANIFEST_JSON)


def _response(
    status_code: int, json_data: dict | None = None, method: str = "GET", url: str = ""
) -> httpx.Response:
    """Build a mocked httpx response that is safe to call raise_for_status on."""
    return httpx.Response(
        status_code,
        json=json_data or {},
        request=httpx.Request(method, url),
    )


def _github_publisher(monkeypatch: pytest.MonkeyPatch) -> GithubPublisher:
    """Build a GithubPublisher with mocked GitHub App token and HTTP responses."""

    private_key_pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("utf-8")
    )

    def fake_post(**kwargs: dict) -> httpx.Response:
        url = str(kwargs.get("url") or "")
        if "/app/installations/" in url:
            return _response(
                200, {"token": "installation-token"}, method="POST", url=url
            )
        if "/git/refs" in url:
            # a branch ref that already exists is tolerated for idempotent retries
            return _response(
                422, {"message": "Reference already exists"}, method="POST", url=url
            )
        if "/pulls" in url:
            # a draft PR that already exists resolves rather than failing
            return _response(
                422, {"message": "Validation Failed"}, method="POST", url=url
            )
        return _response(200, {"sha": "abc123"}, method="POST", url=url)

    def fake_get(**kwargs: dict) -> httpx.Response:
        url = str(kwargs.get("url") or "")
        if "/git/ref" in url:
            return _response(200, {"object": {"sha": "abc123"}}, method="GET", url=url)
        if "/pulls" in url:
            return _response(
                200,
                [
                    {
                        "html_url": "https://github.com/owner/repo/pull/9",
                        "head": {"ref": "draft/demo"},
                        "base": {"ref": "main"},
                    }
                ],
                method="GET",
                url=url,
            )
        return _response(200, {}, method="GET", url=url)

    def fake_put(**kwargs: dict) -> httpx.Response:
        url = str(kwargs.get("url") or "")
        return _response(200, {"content": {}}, method="PUT", url=url)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "put", fake_put)

    return GithubPublisher(
        app_id="app-id",
        client_id="client-id",
        installation_id="123456",
        private_key=private_key_pem,
        owner="owner",
        repo="repo",
    )


def test_github_publish_reuses_existing_draft_pr_on_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 422 from draft PR creation resolves the existing draft PR instead."""

    publisher = _github_publisher(monkeypatch)

    draft_pr_url = publisher.create_draft_pr(
        files={"site/_posts/demo.md": b"post"},
        title="Publish draft: demo",
        body="body",
        branch="draft/demo",
        base="main",
    )

    assert draft_pr_url == "https://github.com/owner/repo/pull/9"


def test_github_publish_creates_draft_pr_when_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean draft PR creation returns the created pull request url."""

    def fake_post(**kwargs: dict) -> httpx.Response:
        url = str(kwargs.get("url") or "")
        if "/app/installations/" in url:
            return _response(
                200, {"token": "installation-token"}, method="POST", url=url
            )
        if "/git/refs" in url:
            return _response(
                201, {"ref": "refs/heads/draft/demo"}, method="POST", url=url
            )
        if "/pulls" in url:
            return _response(
                201,
                {"html_url": "https://github.com/owner/repo/pull/9"},
                method="POST",
                url=url,
            )
        return _response(200, {"sha": "abc123"}, method="POST", url=url)

    def fake_get(**kwargs: dict) -> httpx.Response:
        return _response(
            200, {"object": {"sha": "abc123"}}, method="GET", url=str(kwargs.get("url"))
        )

    def fake_put(**kwargs: dict) -> httpx.Response:
        return _response(200, {"content": {}}, method="PUT", url=str(kwargs.get("url")))

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "put", fake_put)

    publisher = GithubPublisher(
        app_id="app-id",
        client_id="client-id",
        installation_id="123456",
        private_key=(
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
            .private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            .decode("utf-8")
        ),
        owner="owner",
        repo="repo",
    )

    draft_pr_url = publisher.create_draft_pr(
        files={"site/_posts/demo.md": b"post"},
        title="Publish draft: demo",
        body="body",
        branch="draft/demo",
        base="main",
    )

    assert draft_pr_url == "https://github.com/owner/repo/pull/9"


def test_draft_files_maps_manifest_to_site_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The draft file map derives the expected site content from a manifest."""

    monkeypatch.chdir(tmp_path)
    Path("og").mkdir()
    (Path("og") / "demo.jpg").write_bytes(b"og-bytes")
    Path("thumb-1.webp").write_bytes(b"thumb-bytes")

    files = _draft_files(
        SimpleNamespace(
            SITE_BUCKET="bucket",
            SET_NAME="demo",
            POST_NAME="2026-11-22-demo",
        ),
        _make_manifest(),
        og_image_path="og/demo.jpg",
        it_image_path="thumb-1.webp",
    )

    manifest = _make_manifest()
    assert files[f"site/_posts/{manifest.post_name}.md"] == manifest.post_draft.encode(
        "utf-8"
    )
    assert files[f"site/assets/streams/{manifest.set}.json"] == json.dumps(
        manifest.image_manifest
    ).encode("utf-8")
    assert files[f"site/_data/set_streams/{manifest.post_name}.json"]
    assert files[f"site/_data/set_posters/{manifest.post_name}.json"]
    assert files[f"site/assets/og/{manifest.set}.jpg"] == b"og-bytes"
    assert (
        files[f"site/assets/img/index-thumbs/{manifest.set_spec.thumb}.webp"]
        == b"thumb-bytes"
    )


def test_just_publish_pr_completes_and_returns_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PR-only task path marks the run completed and exits zero on success."""

    monkeypatch.chdir(tmp_path)
    settings = FakeSettings()
    s3 = FakeS3(spec_json=MANIFEST_JSON)
    admin = FakeAdminAPI()
    github = FakeGithubPublish()

    monkeypatch.setattr("publish.publish.github_publish", github)

    exit_code = _just_publish_pr(s3, settings, admin)

    assert exit_code == 0
    assert len(github.calls) == 1
    assert github.calls[0]["manifest"] == _make_manifest()
    assert github.calls[0]["og_image_path"] == "demo.jpg"
    assert github.calls[0]["it_image_path"] == "thumb-1.webp"
    assert s3.downloads[0] == ("drafts/2026-11-22-demo/spec.json", "spec.json")
    assert admin.calls[-1][0] == Status.COMPLETED
    assert admin.calls[-1][2] == {
        "draft_pr_url": "https://github.com/owner/repo/pull/9"
    }


def test_just_publish_pr_fails_and_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PR-only task path marks the run failed and exits one on error."""

    monkeypatch.chdir(tmp_path)
    settings = FakeSettings()
    s3 = FakeS3(spec_json=MANIFEST_JSON)
    admin = FakeAdminAPI()

    def failing_github_publish(**kwargs: dict) -> str:
        """Always fail like a transient GitHub API error."""
        raise RuntimeError("github unavailable")

    monkeypatch.setattr("publish.publish.github_publish", failing_github_publish)

    exit_code = _just_publish_pr(s3, settings, admin)

    assert exit_code == 1
    assert admin.calls[-1][0] == Status.FAILED
    assert admin.calls[-1][2]["error_class"] == "RuntimeError"


def test_just_publish_pr_marks_failed_on_s3_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PR-only task path marks the run failed when an S3 fetch fails."""

    class FailingS3:
        """Fake S3 client that fails like a transient boto3 ClientError."""

        def download_file(self, **kwargs: dict) -> None:
            """Always fail like a missing S3 object."""
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

    monkeypatch.chdir(tmp_path)
    settings = FakeSettings()
    s3 = FailingS3()
    admin = FakeAdminAPI()

    exit_code = _just_publish_pr(s3, settings, admin)

    assert exit_code == 1
    assert admin.calls[-1][0] == Status.FAILED
    assert admin.calls[-1][2]["error_class"] == "ClientError"


def test_handle_github_pr_only_exits_with_pr_only_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The publish task command in github_pr_only mode exits via the PR-only result."""

    monkeypatch.chdir(tmp_path)
    settings = FakeSettings()
    s3 = FakeS3(spec_json=MANIFEST_JSON)
    admin = FakeAdminAPI()
    github = FakeGithubPublish()

    monkeypatch.setattr(
        "publish.publish.PublishSettings", lambda *args, **kwargs: settings
    )
    monkeypatch.setattr("publish.publish.AdminAPI", lambda *args, **kwargs: admin)
    monkeypatch.setattr(
        "publish.publish.boto3", SimpleNamespace(client=lambda *args, **kwargs: s3)
    )
    monkeypatch.setattr("publish.publish.github_publish", github)

    args = SimpleNamespace(run_id=uuid4(), extra_details=None, github_pr_only=True)

    with pytest.raises(SystemExit) as excinfo:
        handle(args)

    assert excinfo.value.code == 0
