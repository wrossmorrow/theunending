"""Tests for the Modal entrypoint's machine-JWT verification."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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


@pytest.fixture
def machine():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from machine_auth import machine_jwt

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
    email = "test-machine@example.iam.gserviceaccount.com"
    kid = "test-kid-123"
    key_json = json.dumps(
        {
            "type": "service_account",
            "private_key": pem,
            "client_email": email,
            "private_key_id": kid,
        }
    )
    audience = "https://admin.theunending.ai"

    token = machine_jwt(key_json, audience)
    return {
        "key_json": key_json,
        "public_pem": public_pem,
        "email": email,
        "kid": kid,
        "audience": audience,
        "token": token,
    }


def _call(module, token, public_pem, monkeypatch, machine):
    from fastapi.security import HTTPAuthorizationCredentials

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", machine["email"])
    monkeypatch.setenv("ADMIN_API_AUDIENCE", machine["audience"])
    monkeypatch.setattr(
        module, "_jwk_client", lambda: _stub_jwk_client(machine["public_pem"])
    )
    return module._check_auth(
        object(), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )


def test_valid_token_accepted(machine, monkeypatch):
    module = load_api_module()
    result = _call(
        module, machine["token"], machine["public_pem"], monkeypatch, machine
    )
    assert result is True


def test_valid_token_carries_kid(machine):
    import jwt as pyjwt

    header = pyjwt.get_unverified_header(machine["token"])
    assert header["kid"] == machine["kid"]


def test_wrong_audience_rejected(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    from machine_auth import machine_jwt

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", machine["email"])
    monkeypatch.setenv("ADMIN_API_AUDIENCE", "https://other.example.com")
    monkeypatch.setattr(
        module, "_jwk_client", lambda: _stub_jwk_client(machine["public_pem"])
    )
    token = machine_jwt(machine["key_json"], machine["audience"])
    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    assert exc_info.value.status_code == 401


def test_garbage_token_rejected(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", machine["email"])
    monkeypatch.setenv("ADMIN_API_AUDIENCE", machine["audience"])
    monkeypatch.setattr(
        module, "_jwk_client", lambda: _stub_jwk_client(machine["public_pem"])
    )

    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt"),
        )
    assert exc_info.value.status_code == 401


def test_missing_issuer_fails_closed(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", raising=False)
    monkeypatch.setenv("ADMIN_API_AUDIENCE", machine["audience"])

    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=machine["token"]),
        )
    assert exc_info.value.status_code == 401
