"""Startup validation for the admin's machine-auth key."""

from __future__ import annotations

import json
from typing import Any


def require_machine_auth(key_json: str | dict[str, Any] | None):
    """Ensure the machine-auth signing key is present and well-formed.

    The admin service mints machine JWTs for every call into the job system;
    running without a valid key (e.g. a missing env var in a deploy) must fail
    loudly at startup rather than silently sending unauthenticated requests.

    Returns the parsed key (dict).
    """
    if not key_json:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_KEY_JSON is not set; refusing to start. "
            "Admin job submissions require a machine JWT key."
        )
    try:
        key = json.loads(key_json) if isinstance(key_json, str) else key_json
    except json.JSONDecodeError as exc:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_KEY_JSON is not valid JSON") from exc
    if not isinstance(key, dict):
        raise TypeError("GOOGLE_SERVICE_ACCOUNT_KEY_JSON must be a JSON object")
    if not isinstance(key.get("private_key"), str) or not key["private_key"].strip():
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_KEY_JSON is missing 'private_key'")
    if not isinstance(key.get("client_email"), str) or not key["client_email"].strip():
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_KEY_JSON is missing 'client_email'")
    return key
