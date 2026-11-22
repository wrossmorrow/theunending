"""Machine-to-machine JWT credentials for the admin API.

Mirrors ``code/src/machine_auth/__init__.py`` (kept self-contained so the admin
service stays independent of the jobs' package). The gateway verifies these
tokens against Google's per-account JWKS endpoint; the private key never
leaves the admin service.
"""

from __future__ import annotations

import json
import time
from typing import Any

import jwt

DEFAULT_LIFETIME_SECONDS = 300


def _load_key(key_json: str | dict[str, Any]) -> tuple[bytes, str, str | None]:
    """Parse a service account key into (private PEM bytes, client email, private key id)."""
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
    """Mint a short-lived RS256 JWT signed as the service account."""
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
