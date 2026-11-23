"""Unit tests for admin startup WIF validation and machine token minting."""

from __future__ import annotations

import base64
import json

import httpx
import pytest
from botocore.credentials import Credentials  # type: ignore[import-untyped]

from api.machine_auth_config import require_machine_auth
from api.utils.machine_auth import (
    AWS_SUBJECT_TOKEN_TYPE,
    GCP_IAM_CREDENTIALS_URL,
    GCP_STS_URL,
    clear_token_cache,
    machine_id_token,
)

TEST_AWS_PROVIDER = (
    "projects/123456789/locations/global/workloadIdentityPools/"
    "theunending-workloads/providers/aws"
)
TEST_SA_EMAIL = "admin-api@thunending-oauth.iam.gserviceaccount.com"
TEST_AUDIENCE = "https://admin.theunending.ai"


class _FakeSession:
    def __init__(self, creds: Credentials | None) -> None:
        self._creds = creds

    def get_credentials(self) -> Credentials | None:
        return self._creds


def _make_fake_jwt(exp: int) -> str:
    def _b64(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{_b64({'alg': 'RS256'})}.{_b64({'exp': exp})}.sig"


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    clear_token_cache()


def test_require_machine_auth_accepts_static_token_or_valid_wif() -> None:
    assert require_machine_auth(None, None, static_token="local-dev-token") is None
    result = require_machine_auth(
        f"//iam.googleapis.com/{TEST_AWS_PROVIDER}", TEST_SA_EMAIL
    )
    assert result is not None
    provider, email = result
    assert provider == TEST_AWS_PROVIDER
    assert email == TEST_SA_EMAIL


def test_require_machine_auth_rejects_missing_or_bad_config() -> None:
    with pytest.raises(ValueError):
        require_machine_auth(None, TEST_SA_EMAIL)
    with pytest.raises(ValueError):
        require_machine_auth(TEST_AWS_PROVIDER, None)
    with pytest.raises(ValueError):
        require_machine_auth("bad-provider", TEST_SA_EMAIL)
    with pytest.raises(ValueError):
        require_machine_auth(TEST_AWS_PROVIDER, "not-an-email")


def test_admin_machine_id_token_aws_wif_and_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MODAL_IDENTITY_TOKEN", raising=False)
    calls = 0
    expected_jwt = _make_fake_jwt(4600)

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if str(request.url) == GCP_STS_URL:
            body = json.loads(request.content)
            assert body["subjectTokenType"] == AWS_SUBJECT_TOKEN_TYPE
            assert body["audience"] == f"//iam.googleapis.com/{TEST_AWS_PROVIDER}"
            return httpx.Response(200, json={"access_token": "sts-token"})
        assert str(request.url) == GCP_IAM_CREDENTIALS_URL.format(email=TEST_SA_EMAIL)
        assert request.headers["authorization"] == "Bearer sts-token"
        assert json.loads(request.content) == {
            "audience": TEST_AUDIENCE,
            "includeEmail": True,
        }
        return httpx.Response(200, json={"token": expected_jwt})

    creds = Credentials("AKIAEXAMPLE", "secret", "session-token")
    session = _FakeSession(creds)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        tok1 = machine_id_token(
            TEST_AWS_PROVIDER,
            TEST_SA_EMAIL,
            TEST_AUDIENCE,
            client=client,
            session=session,
            now=1000.0,
        )
        tok2 = machine_id_token(
            TEST_AWS_PROVIDER,
            TEST_SA_EMAIL,
            TEST_AUDIENCE,
            client=client,
            session=session,
            now=2000.0,
        )

    assert tok1 == expected_jwt
    assert tok2 == expected_jwt
    assert calls == 2
