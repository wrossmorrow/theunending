from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from machine_auth import machine_jwks, machine_jwt, service_account_email


def _test_key_json():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "abc123",
        "private_key": pem,
        "client_email": "admin-jobs@test-project.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_machine_jwt_round_trip():
    key_json = _test_key_json()
    audience = "https://admin.theunending.ai"

    token = machine_jwt(
        json.dumps(key_json), audience, lifetime_seconds=60, now=int(time.time())
    )
    assert isinstance(token, str) and token

    jwks = machine_jwks(key_json)
    email = service_account_email(key_json)
    assert email == "admin-jobs@test-project.iam.gserviceaccount.com"

    # verify against the public key from the derived JWKS
    jwks_key = jwks["keys"][0]
    pem = _pem_from_jwks(jwks_key)
    payload = jwt.decode(
        token,
        pem,
        algorithms=["RS256"],
        audience=audience,
        issuer=email,
    )
    assert payload["iss"] == email
    assert payload["sub"] == email
    assert payload["aud"] == audience
    assert payload["exp"] - payload["iat"] == 60


def test_machine_jwks_matches_private_key():
    key_json = _test_key_json()
    private_key = serialization.load_pem_private_key(
        key_json["private_key"].encode("utf-8"), password=None
    )
    expected_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    # the derived JWKS must verify a token signed by this private key
    jwks = machine_jwks(key_json)
    assert _pem_from_jwks(jwks["keys"][0]) == expected_pem
    token = machine_jwt(key_json, "https://admin.theunending.ai")
    payload = jwt.decode(
        token,
        expected_pem,
        algorithms=["RS256"],
        audience="https://admin.theunending.ai",
        issuer=service_account_email(key_json),
    )
    assert payload["sub"] == service_account_email(key_json)


def test_machine_jwt_rejects_bad_inputs():
    with pytest.raises(ValueError):
        machine_jwt("not json", "https://admin.theunending.ai")
    with pytest.raises(ValueError):
        machine_jwt(
            json.dumps({"client_email": "x@test"}), "https://admin.theunending.ai"
        )
    with pytest.raises(ValueError):
        machine_jwt(json.dumps(_test_key_json()), "")
    with pytest.raises(TypeError):
        machine_jwt(42, "https://admin.theunending.ai")


def _pem_from_jwks(jwk: dict) -> str:
    def b64url_int(value: str) -> int:
        padded = value + "=" * (-len(value) % 4)
        return int.from_bytes(base64.urlsafe_b64decode(padded), "big")

    public_numbers = rsa.RSAPublicNumbers(
        e=b64url_int(jwk["e"]), n=b64url_int(jwk["n"])
    )
    public_key = public_numbers.public_key()
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
