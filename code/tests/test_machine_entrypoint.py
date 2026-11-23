"""Tests for the Modal entrypoint's Google OIDC machine-token verification."""

import importlib.util
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

REPO = Path(__file__).parents[1]


def load_api_module():
    spec = importlib.util.spec_from_file_location(
        "modal_api", REPO / "modal" / "api.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["modal_api"] = module
    spec.loader.exec_module(module)
    return module


def _stub_jwk_client(public_pem):
    class _Stub:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=public_pem)

    return _Stub()


def _mint_oidc_token(
    private_pem: str,
    *,
    email: str,
    email_verified: bool = True,
    audience: str = "https://admin.theunending.ai",
    issuer: str = "https://accounts.google.com",
    kid: str = "google-oidc-kid-1",
) -> str:
    now = int(time.time())
    payload = {
        "iss": issuer,
        "sub": "109876543210987654321",
        "email": email,
        "email_verified": email_verified,
        "aud": audience,
        "iat": now,
        "exp": now + 3600,
    }
    return pyjwt.encode(
        payload, private_pem, algorithm="RS256", headers={"kid": kid}
    )


@pytest.fixture
def oidc_machine():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    email = "admin-api@thunending-oauth.iam.gserviceaccount.com"
    audience = "https://admin.theunending.ai"
    token = _mint_oidc_token(pem, email=email, audience=audience)
    return {
        "private_pem": pem,
        "public_pem": public_pem,
        "email": email,
        "audience": audience,
        "token": token,
    }


def _call(module, token, monkeypatch, machine, *, aud_env: str = "ADMIN_API_AUDIENCE"):
    from fastapi.security import HTTPAuthorizationCredentials

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", machine["email"])
    monkeypatch.setenv(aud_env, machine["audience"])
    monkeypatch.setattr(
        module, "_jwk_client", lambda: _stub_jwk_client(machine["public_pem"])
    )
    return module._check_auth(
        object(), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )


def test_valid_oidc_token_accepted(oidc_machine, monkeypatch):
    module = load_api_module()
    assert _call(module, oidc_machine["token"], monkeypatch, oidc_machine) is True


def test_wrong_audience_rejected(oidc_machine, monkeypatch):
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    module = load_api_module()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", oidc_machine["email"])
    monkeypatch.setenv("MODAL_API_AUDIENCE", "https://other.example.com")
    monkeypatch.setattr(
        module, "_jwk_client", lambda: _stub_jwk_client(oidc_machine["public_pem"])
    )

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=oidc_machine["token"]
            ),
        )
    assert exc_info.value.status_code == 401


def test_wrong_email_rejected(oidc_machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    token = _mint_oidc_token(
        oidc_machine["private_pem"],
        email="other-sa@thunending-oauth.iam.gserviceaccount.com",
        audience=oidc_machine["audience"],
    )
    with pytest.raises(HTTPException) as exc_info:
        _call(module, token, monkeypatch, oidc_machine)
    assert exc_info.value.status_code == 401


def test_unverified_email_rejected(oidc_machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    token = _mint_oidc_token(
        oidc_machine["private_pem"],
        email=oidc_machine["email"],
        email_verified=False,
        audience=oidc_machine["audience"],
    )
    with pytest.raises(HTTPException) as exc_info:
        _call(module, token, monkeypatch, oidc_machine)
    assert exc_info.value.status_code == 401


def test_wrong_issuer_rejected(oidc_machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    token = _mint_oidc_token(
        oidc_machine["private_pem"],
        email=oidc_machine["email"],
        audience=oidc_machine["audience"],
        issuer="https://evil.example.com",
    )
    with pytest.raises(HTTPException) as exc_info:
        _call(module, token, monkeypatch, oidc_machine)
    assert exc_info.value.status_code == 401


def test_garbage_token_rejected(oidc_machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    with pytest.raises(HTTPException) as exc_info:
        _call(module, "not-a-jwt", monkeypatch, oidc_machine)
    assert exc_info.value.status_code == 401


def test_missing_email_fails_closed(oidc_machine, monkeypatch):
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    module = load_api_module()
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", raising=False)
    monkeypatch.setenv("ADMIN_API_AUDIENCE", oidc_machine["audience"])

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(
                scheme="Bearer", credentials=oidc_machine["token"]
            ),
        )
    assert exc_info.value.status_code == 401


def test_jwk_client_is_cached():
    module = load_api_module()
    module._jwk_client.cache_clear()
    first = module._jwk_client()
    second = module._jwk_client()
    assert first is second
    assert module._jwk_client.cache_info().hits == 1
