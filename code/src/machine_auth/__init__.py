"""Machine-to-machine OIDC ID token credentials via GCP Workload Identity Federation.

Workloads (AWS EC2/Fargate via SigV4 GetCallerIdentity, Modal via
``MODAL_IDENTITY_TOKEN`` OIDC) exchange their native identity at Google STS for
a federated access token, then call IAM Credentials ``generateIdToken`` to mint
a Google-signed OIDC ID token for a zero-permission service account.

No service account private keys are created or stored anywhere. Tokens are
cached in memory per ``(wif_provider, service_account_email, audience)`` and
refreshed automatically before expiry.
"""

from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import urllib.parse
from typing import Any

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

GCP_STS_URL = "https://sts.googleapis.com/v1/token"
GCP_IAM_CREDENTIALS_URL = (
    "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
    "{email}:generateIdToken"
)
AWS_SUBJECT_TOKEN_TYPE = "urn:ietf:params:aws:token-type:aws4_request"
OIDC_SUBJECT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"

DEFAULT_ID_TOKEN_LIFETIME_SECONDS = 3600
DEFAULT_REFRESH_MARGIN_SECONDS = 300

_WIF_PROVIDER_RE = re.compile(
    r"^projects/[^/\s]+/locations/[^/\s]+/workloadIdentityPools/[^/\s]+/providers/[^/\s]+$"
)

_CACHE_LOCK = threading.Lock()
_TOKEN_CACHE: dict[tuple[str, str, str], tuple[str, float]] = {}


def clear_token_cache() -> None:
    """Clear the in-memory machine ID token cache (primarily for tests)."""
    with _CACHE_LOCK:
        _TOKEN_CACHE.clear()


def normalize_wif_provider(wif_provider: str | None) -> str:
    """Normalize and validate a GCP Workload Identity Provider resource name."""
    if not isinstance(wif_provider, str) or not wif_provider.strip():
        raise ValueError("GCP_WIF_PROVIDER is not set")
    provider = wif_provider.strip()
    provider = provider.removeprefix("//iam.googleapis.com/")
    provider = provider.lstrip("/")
    if not _WIF_PROVIDER_RE.match(provider):
        raise ValueError(
            "GCP_WIF_PROVIDER must match "
            "'projects/<project>/locations/<loc>/workloadIdentityPools/<pool>/providers/<provider>'"
        )
    return provider


def validate_wif_config(
    wif_provider: str | None,
    service_account_email: str | None,
) -> tuple[str, str]:
    """Validate non-secret WIF provider and target service account email."""
    provider = normalize_wif_provider(wif_provider)
    if not isinstance(service_account_email, str) or not service_account_email.strip():
        raise ValueError("GCP_SERVICE_ACCOUNT_EMAIL is not set")
    email = service_account_email.strip()
    if "@" not in email or "/" in email or any(ch.isspace() for ch in email):
        raise ValueError("GCP_SERVICE_ACCOUNT_EMAIL must be a valid email address")
    return provider, email


def _aws_subject_token(
    wif_provider: str,
    region: str = "us-east-1",
    *,
    session: Any | None = None,
) -> str:
    """Build a URL-encoded AWS SigV4 GetCallerIdentity subject token for GCP STS."""
    active_session = session if session is not None else boto3.Session()
    creds = active_session.get_credentials()
    if creds is None:
        raise RuntimeError(
            "AWS credentials are not available for GCP Workload Identity Federation"
        )
    frozen = creds.get_frozen_credentials()

    sts_host = f"sts.{region}.amazonaws.com"
    sts_url = f"https://{sts_host}/?Action=GetCallerIdentity&Version=2011-06-15"
    target_resource = f"//iam.googleapis.com/{wif_provider}"

    request = AWSRequest(
        method="POST",
        url=sts_url,
        headers={
            "Host": sts_host,
            "x-goog-cloud-target-resource": target_resource,
        },
    )
    SigV4Auth(frozen, "sts", region).add_auth(request)

    token_payload = {
        "url": request.url,
        "method": request.method,
        "headers": [{"key": str(k), "value": str(v)} for k, v in request.headers.items()],
    }
    return urllib.parse.quote(json.dumps(token_payload), safe="")


def _post_json(
    url: str,
    *,
    json_body: dict[str, Any],
    headers: dict[str, str] | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if client is not None:
        response = client.post(url, json=json_body, headers=headers)
    else:
        with httpx.Client(timeout=10.0) as tmp_client:
            response = tmp_client.post(url, json=json_body, headers=headers)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise TypeError(f"Expected JSON object from {url}")
    return data


def _exchange_sts_token(
    wif_provider: str,
    subject_token: str,
    subject_token_type: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    data = _post_json(
        GCP_STS_URL,
        json_body={
            "audience": f"//iam.googleapis.com/{wif_provider}",
            "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
            "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
            "scope": "https://www.googleapis.com/auth/cloud-platform",
            "subjectTokenType": subject_token_type,
            "subjectToken": subject_token,
        },
        client=client,
    )
    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise RuntimeError("GCP STS response is missing 'access_token'")
    return access_token


def _generate_id_token(
    access_token: str,
    service_account_email: str,
    audience: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    url = GCP_IAM_CREDENTIALS_URL.format(email=service_account_email)
    data = _post_json(
        url,
        json_body={"audience": audience, "includeEmail": True},
        headers={"Authorization": f"Bearer {access_token}"},
        client=client,
    )
    token = data.get("token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("GCP generateIdToken response is missing 'token'")
    return token


def _jwt_expiry(token: str, default_exp: float) -> float:
    parts = token.split(".")
    if len(parts) != 3:
        return default_exp
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:  # noqa: BLE001
        return default_exp
    if isinstance(payload, dict):
        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and not isinstance(exp, bool):
            return float(exp)
    return default_exp


def machine_id_token(
    wif_provider: str | None,
    service_account_email: str | None,
    audience: str,
    *,
    modal_identity_token: str | None = None,
    aws_region: str | None = None,
    client: httpx.Client | None = None,
    session: Any | None = None,
    now: float | None = None,
    refresh_margin_seconds: int = DEFAULT_REFRESH_MARGIN_SECONDS,
) -> str:
    """Mint (or return cached) Google OIDC ID token via Workload Identity Federation."""
    if not isinstance(audience, str) or not audience.strip():
        raise ValueError("audience is required")
    clean_audience = audience.strip()
    provider, email = validate_wif_config(wif_provider, service_account_email)

    current_time = time.time() if now is None else now
    cache_key = (provider, email, clean_audience)

    with _CACHE_LOCK:
        cached = _TOKEN_CACHE.get(cache_key)
        if cached is not None:
            cached_token, cached_exp = cached
            if current_time < cached_exp - refresh_margin_seconds:
                return cached_token

        oidc_token = (
            modal_identity_token
            if modal_identity_token is not None
            else os.environ.get("MODAL_IDENTITY_TOKEN") or ""
        ).strip()
        if oidc_token:
            subject_token = oidc_token
            subject_token_type = OIDC_SUBJECT_TOKEN_TYPE
        else:
            region = (
                aws_region
                or os.environ.get("AWS_REGION")
                or os.environ.get("AWS_DEFAULT_REGION")
                or "us-east-1"
            ).strip()
            subject_token = _aws_subject_token(
                provider, region=region, session=session
            )
            subject_token_type = AWS_SUBJECT_TOKEN_TYPE

        access_token = _exchange_sts_token(
            provider, subject_token, subject_token_type, client=client
        )
        id_token = _generate_id_token(
            access_token, email, clean_audience, client=client
        )
        exp = _jwt_expiry(
            id_token, default_exp=current_time + DEFAULT_ID_TOKEN_LIFETIME_SECONDS
        )
        _TOKEN_CACHE[cache_key] = (id_token, exp)
        return id_token


def machine_id_token_from_env(
    audience: str,
    *,
    client: httpx.Client | None = None,
    aws_region: str | None = None,
) -> str:
    """Return ``GOOGLE_MACHINE_ID_TOKEN`` if set, else mint via WIF env vars."""
    static_token = (os.environ.get("GOOGLE_MACHINE_ID_TOKEN") or "").strip()
    if static_token:
        return static_token
    return machine_id_token(
        os.environ.get("GCP_WIF_PROVIDER"),
        os.environ.get("GCP_SERVICE_ACCOUNT_EMAIL"),
        audience,
        client=client,
        aws_region=aws_region,
    )
