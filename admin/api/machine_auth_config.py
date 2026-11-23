"""Startup validation for the admin's machine-auth WIF configuration."""

from __future__ import annotations

from api.utils.machine_auth import validate_wif_config


def require_machine_auth(
    wif_provider: str | None,
    service_account_email: str | None,
    static_token: str | None = None,
) -> tuple[str, str] | None:
    """Ensure WIF machine-auth configuration (or a local static token override) is valid.

    The admin service mints Google OIDC ID tokens via Workload Identity Federation
    for every call into the job system; running without valid config (e.g. missing
    env vars in a deploy) must fail loudly at startup rather than silently sending
    unauthenticated requests.
    """
    if isinstance(static_token, str) and static_token.strip():
        return None
    if not wif_provider or not service_account_email:
        raise ValueError(
            "GCP_WIF_PROVIDER and GCP_SERVICE_ACCOUNT_EMAIL must be set "
            "(or GOOGLE_MACHINE_ID_TOKEN for local dev); refusing to start."
        )
    return validate_wif_config(wif_provider, service_account_email)
