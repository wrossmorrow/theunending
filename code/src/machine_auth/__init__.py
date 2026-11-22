"""Machine-to-machine JWT credentials via a Google service account.

Callers mint short-lived RS256 JWTs with a service account; the gateway
(and the Modal public endpoint) verify them against Google's per-account JWKS
endpoint. The private key never leaves the machines that mint tokens. Minting
happens per request, not once, and each token carries a ``kid`` header matching
the key Google publishes for the account (so verifiers pick the right key
during a rotation).
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization

DEFAULT_LIFETIME_SECONDS = 300


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_key(key_json: str | dict[str, Any]) -> tuple[bytes, str, str | None]:
    """Parse a service account key (JSON string or parsed dict) into
    (private PEM bytes, client email, private key id).

    The key id is optional; Google-issued keys carry it, so tokens can be
    stamped with ``kid`` for rotation-aware verification.
    """
    if isinstance(key_json, str):
        try:
            key = json.loads(key_json)
        except json.JSONDecodeError as exc:
            raise ValueError("service account key JSON is not valid JSON") from exc
    else:
        key = key_json
    if not isinstance(key, dict):
        raise TypeError("service account key must be a JSON object")

    pem = key.get("private_key")
    email = key.get("client_email")
    if not isinstance(pem, str) or not pem.strip():
        raise ValueError("service account key is missing 'private_key'")
    if not isinstance(email, str) or not email.strip():
        raise ValueError("service account key is missing 'client_email'")
    kid = key.get("private_key_id")
    return (
        pem.encode("utf-8"),
        email,
        (kid if isinstance(kid, str) and kid.strip() else None),
    )


def machine_jwt(
    key_json: str | dict[str, Any],
    audience: str,
    lifetime_seconds: int = DEFAULT_LIFETIME_SECONDS,
    *,
    now: int | None = None,
) -> str:
    """Mint a short-lived RS256 JWT for a service account.

    The ``iss``/``sub`` are the service account's email and ``aud`` is the
    audience the token is intended for (the admin API root). The token is kept
    deliberately minimal: the gateway matches ``iss`` (the service account), not
    any user identity.
    """
    if not isinstance(audience, str) or not audience.strip():
        raise ValueError("audience is required")

    pem, email, kid = _load_key(key_json)
    if now is None:
        now = int(time.time())

    payload = {
        "iss": email,
        "sub": email,
        "aud": audience,
        "iat": now,
        "exp": now + lifetime_seconds,
    }
    headers = {"kid": kid} if kid else None
    return jwt.encode(payload, pem, algorithm="RS256", headers=headers)


def machine_jwks(key_json: str | dict[str, Any]) -> dict[str, Any]:
    """Derive the public JWKS for the private key (safe to distribute to the verifier)."""
    pem, _, kid = _load_key(key_json)
    private_key = serialization.load_pem_private_key(pem, password=None)
    numbers = private_key.public_key().public_numbers()

    n = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    e = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url(n),
        "e": _b64url(e),
    }
    if kid:
        jwk["kid"] = kid
    return {"keys": [jwk]}


def service_account_email(key_json: str | dict[str, Any]) -> str:
    """Return the service account email (``client_email``) from a key payload."""
    _, email, _ = _load_key(key_json)
    return email
