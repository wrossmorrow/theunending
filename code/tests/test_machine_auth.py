from __future__ import annotations

import base64
import json
import urllib.parse

import httpx
import pytest
from botocore.credentials import Credentials

from machine_auth import (
    AWS_SUBJECT_TOKEN_TYPE,
    GCP_IAM_CREDENTIALS_URL,
    GCP_STS_URL,
    OIDC_SUBJECT_TOKEN_TYPE,
    _aws_subject_token,
    clear_token_cache,
    machine_id_token,
    machine_id_token_from_env,
    validate_wif_config,
)

TEST_AWS_PROVIDER = (
    "projects/123456789/locations/global/workloadIdentityPools/"
    "theunending-workloads/providers/aws"
)
TEST_MODAL_PROVIDER = (
    "projects/123456789/locations/global/workloadIdentityPools/"
    "theunending-workloads/providers/modal"
)
TEST_SA_EMAIL = "publish-job@thunending-oauth.iam.gserviceaccount.com"
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


def test_aws_subject_token_format() -> None:
    creds = Credentials(
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "session-token-123",
    )
    encoded = _aws_subject_token(
        TEST_AWS_PROVIDER, region="us-east-1", session=_FakeSession(creds)
    )
    payload = json.loads(urllib.parse.unquote(encoded))

    assert payload["method"] == "POST"
    assert (
        payload["url"]
        == "https://sts.us-east-1.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15"
    )
    headers = {item["key"].lower(): item["value"] for item in payload["headers"]}
    assert headers["host"] == "sts.us-east-1.amazonaws.com"
    assert (
        headers["x-goog-cloud-target-resource"]
        == f"//iam.googleapis.com/{TEST_AWS_PROVIDER}"
    )
    assert headers["x-amz-security-token"] == "session-token-123"
    assert "x-amz-date" in headers
    assert headers["authorization"].startswith("AWS4-HMAC-SHA256 ")
    assert "x-goog-cloud-target-resource" in headers["authorization"]


def test_modal_oidc_exchange(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODAL_IDENTITY_TOKEN", raising=False)
    calls: list[tuple[str, dict, dict]] = []
    expected_token = _make_fake_jwt(4600)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append((str(request.url), dict(request.headers), body))
        if str(request.url) == GCP_STS_URL:
            return httpx.Response(200, json={"access_token": "sts-access-token"})
        if str(request.url) == GCP_IAM_CREDENTIALS_URL.format(email=TEST_SA_EMAIL):
            return httpx.Response(200, json={"token": expected_token})
        raise AssertionError(f"Unexpected URL: {request.url}")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        token = machine_id_token(
            TEST_MODAL_PROVIDER,
            TEST_SA_EMAIL,
            TEST_AUDIENCE,
            modal_identity_token="modal-oidc-jwt",
            client=client,
            now=1000.0,
        )

    assert token == expected_token
    assert len(calls) == 2

    sts_url, _, sts_body = calls[0]
    assert sts_url == GCP_STS_URL
    assert sts_body == {
        "audience": f"//iam.googleapis.com/{TEST_MODAL_PROVIDER}",
        "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
        "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "https://www.googleapis.com/auth/cloud-platform",
        "subjectTokenType": OIDC_SUBJECT_TOKEN_TYPE,
        "subjectToken": "modal-oidc-jwt",
    }

    iam_url, iam_headers, iam_body = calls[1]
    assert iam_url == GCP_IAM_CREDENTIALS_URL.format(email=TEST_SA_EMAIL)
    assert iam_headers["authorization"] == "Bearer sts-access-token"
    assert iam_body == {"audience": TEST_AUDIENCE, "includeEmail": True}


def test_token_caching_and_refresh_margin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODAL_IDENTITY_TOKEN", raising=False)
    minted = [_make_fake_jwt(4600), _make_fake_jwt(8200)]
    iam_calls = 0
    total_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal iam_calls, total_calls
        total_calls += 1
        if str(request.url) == GCP_STS_URL:
            body = json.loads(request.content)
            assert body["subjectTokenType"] == AWS_SUBJECT_TOKEN_TYPE
            return httpx.Response(200, json={"access_token": f"sts-{iam_calls}"})
        tok = minted[iam_calls]
        iam_calls += 1
        return httpx.Response(200, json={"token": tok})

    creds = Credentials("AKIAEXAMPLE", "secret", "tok")
    session = _FakeSession(creds)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = machine_id_token(
            TEST_AWS_PROVIDER,
            TEST_SA_EMAIL,
            TEST_AUDIENCE,
            client=client,
            session=session,
            now=1000.0,
        )
        # Just before exp - 300 (4600 - 300 = 4300): must hit cache
        second = machine_id_token(
            TEST_AWS_PROVIDER,
            TEST_SA_EMAIL,
            TEST_AUDIENCE,
            client=client,
            session=session,
            now=4299.0,
        )
        # Inside refresh margin (4300 >= 4600 - 300): must refresh
        third = machine_id_token(
            TEST_AWS_PROVIDER,
            TEST_SA_EMAIL,
            TEST_AUDIENCE,
            client=client,
            session=session,
            now=4300.0,
        )

    assert first == minted[0]
    assert second == minted[0]
    assert third == minted[1]
    assert total_calls == 4


def test_machine_id_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_MACHINE_ID_TOKEN", "static-local-token")
    assert machine_id_token_from_env(TEST_AUDIENCE) == "static-local-token"

    monkeypatch.delenv("GOOGLE_MACHINE_ID_TOKEN")
    monkeypatch.setenv("GCP_WIF_PROVIDER", TEST_MODAL_PROVIDER)
    monkeypatch.setenv("GCP_SERVICE_ACCOUNT_EMAIL", TEST_SA_EMAIL)
    monkeypatch.setenv("MODAL_IDENTITY_TOKEN", "modal-env-jwt")

    expected = _make_fake_jwt(9999999999)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == GCP_STS_URL:
            return httpx.Response(200, json={"access_token": "sts-env"})
        return httpx.Response(200, json={"token": expected})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert machine_id_token_from_env(TEST_AUDIENCE, client=client) == expected


def test_validate_wif_config_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODAL_IDENTITY_TOKEN", raising=False)
    provider, email = validate_wif_config(
        f"//iam.googleapis.com/{TEST_AWS_PROVIDER}",
        f" {TEST_SA_EMAIL} ",
    )
    assert provider == TEST_AWS_PROVIDER
    assert email == TEST_SA_EMAIL

    with pytest.raises(ValueError):
        validate_wif_config("", TEST_SA_EMAIL)
    with pytest.raises(ValueError):
        validate_wif_config("projects/only-project", TEST_SA_EMAIL)
    with pytest.raises(ValueError):
        validate_wif_config(TEST_AWS_PROVIDER, "not-an-email")
    with pytest.raises(ValueError):
        machine_id_token(TEST_AWS_PROVIDER, TEST_SA_EMAIL, "")
    with pytest.raises(RuntimeError):
        _aws_subject_token(TEST_AWS_PROVIDER, session=_FakeSession(None))
