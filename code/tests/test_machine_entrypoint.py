"""Tests for the Modal entrypoint's machine-JWT verification."""

import importlib.util
import json
import sys
from pathlib import Path

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


@pytest.fixture
def machine():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from machine_auth import machine_jwks

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    email = "test-machine@example.iam.gserviceaccount.com"
    key_json = json.dumps(
        {"type": "service_account", "private_key": pem, "client_email": email}
    )
    audience = "https://admin.theunending.ai"

    from machine_auth import machine_jwt

    token = machine_jwt(key_json, audience)
    jwks = machine_jwks(key_json)
    return key_json, email, audience, token, jwks


def _call(module, token, monkeypatch, machine):
    from fastapi.security import HTTPAuthorizationCredentials

    _, email, audience, _, jwks = machine
    monkeypatch.setenv("GOOGLE_MACHINE_JWKS", json.dumps(jwks))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", email)
    monkeypatch.setenv("ADMIN_API_AUDIENCE", audience)
    return module._check_auth(
        object(), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    )


def test_valid_token_accepted(machine, monkeypatch):

    module = load_api_module()
    result = _call(module, machine[3], monkeypatch, machine)
    assert result is True


def test_wrong_audience_rejected(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    _, email, audience, _, _ = machine
    monkeypatch.setenv("GOOGLE_MACHINE_JWKS", json.dumps(machine[4]))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", email)
    monkeypatch.setenv("ADMIN_API_AUDIENCE", "https://other.example.com")

    from machine_auth import machine_jwt

    token = machine_jwt(machine[0], audience)
    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(), HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    assert exc_info.value.status_code == 401


def test_garbage_token_rejected(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    _, email, audience, _, jwks = machine
    monkeypatch.setenv("GOOGLE_MACHINE_JWKS", json.dumps(jwks))
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", email)
    monkeypatch.setenv("ADMIN_API_AUDIENCE", audience)

    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt"),
        )
    assert exc_info.value.status_code == 401


def test_missing_jwks_fails_closed(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", machine[1])
    monkeypatch.setenv("ADMIN_API_AUDIENCE", machine[2])
    monkeypatch.delenv("GOOGLE_MACHINE_JWKS", raising=False)

    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=machine[3]),
        )
    assert exc_info.value.status_code == 401


def test_missing_issuer_fails_closed(machine, monkeypatch):
    from fastapi import HTTPException

    module = load_api_module()
    monkeypatch.setenv("GOOGLE_MACHINE_JWKS", json.dumps(machine[4]))
    monkeypatch.setenv("ADMIN_API_AUDIENCE", machine[2])
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", raising=False)

    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(HTTPException) as exc_info:
        module._check_auth(
            object(),
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=machine[3]),
        )
    assert exc_info.value.status_code == 401
