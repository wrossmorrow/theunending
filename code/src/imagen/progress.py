import os
from collections.abc import Collection
from enum import StrEnum
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    retry_if_result,
    stop_after_attempt,
    wait_exponential,
)

from machine_auth import machine_jwt

DEFAULT_RETRY_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
)

DEFAULT_RETRY_STATUS_CODES: set[int] = {429, 500, 502, 503, 504}

BACKOFF_MULTIPLIER = 1
BACKOFF_MINIMUM = 1
BACKOFF_MAXIMUM = 10
DEFAULT_MAX_ATTEMPTS = 3


class Status(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _request_with_retry(
    method: str,
    url: str,
    *,
    client: httpx.Client | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_status_codes: Collection[int] = DEFAULT_RETRY_STATUS_CODES,
    retry_exceptions: tuple[type[Exception], ...] = DEFAULT_RETRY_EXCEPTIONS,
    **kwargs: Any,
) -> httpx.Response:
    """
    Executes an HTTP request using httpx with tenacity exponential backoff.
    Retries on specified exceptions and HTTP status codes up to `max_attempts`.
    """

    def is_retryable_status(response: httpx.Response) -> bool:
        return response.status_code in retry_status_codes

    # Combine exception-based and result-based retry triggers
    retry_strategy = Retrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=BACKOFF_MULTIPLIER,
            min=BACKOFF_MINIMUM,
            max=BACKOFF_MAXIMUM,
        ),
        retry=(
            retry_if_exception_type(retry_exceptions)
            | retry_if_result(is_retryable_status)
        ),
        reraise=True,
    )

    def _do_request(active_client: httpx.Client) -> httpx.Response:
        for attempt in retry_strategy:
            with attempt:
                response = active_client.request(method, url, **kwargs)
                return response
        # Fallback type safety (unreachable when reraise=True)
        raise RuntimeError("Retry loop exited unexpectedly")

    # Use provided client for connection pooling, or create a temporary one
    if client is not None:
        response = _do_request(client)
    else:
        with httpx.Client() as temp_client:
            response = _do_request(temp_client)

    # Raise HTTPStatusError if the final response is still an error (e.g., 404, or exhausted 503)
    response.raise_for_status()
    return response


def _update_progress(
    client: httpx.Client,
    url: str,
    status: Status,
    message: str,
    details: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    _ = _request_with_retry(
        method="PUT",
        url=url,
        client=client,
        headers=headers,
        json={
            "status": status,
            "message": message,
            "details": details,
        },
    )


DEFAULT_ADMIN_API_AUDIENCE = "https://admin.theunending.ai"


def _admin_api_audience() -> str:
    return (
        os.environ.get("ADMIN_API_AUDIENCE") or ""
    ).strip() or DEFAULT_ADMIN_API_AUDIENCE


def _machine_token() -> str:
    """Mint a fresh machine JWT for the admin API from the service account key."""
    key = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY_JSON")
    if not key or not key.strip():
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_KEY_JSON is not set; "
            "admin status updates require it"
        )
    return machine_jwt(key, _admin_api_audience())


class AdminAPI:
    def __init__(
        self,
        url: str | None,
        admin_run_id: str | None,
    ) -> None:
        self._url = url
        self._admin_run_id = admin_run_id
        self._http = httpx.Client() if url is not None else None

    def _headers(self) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": f"Bearer {_machine_token()}",
        }
        if self._admin_run_id is not None:
            headers["x-admin-run-id"] = self._admin_run_id
        return headers

    def update_progress(
        self,
        status: Status,
        message: str,
        details: dict | None = None,
    ) -> None:
        if self._url is None:
            print(
                f"No url set for status updates, no call will be made ({status}, {message}, {details})"
            )
            return

        try:
            return _update_progress(
                client=self._http,
                url=self._url,
                status=status,
                message=message,
                details=details,
                headers=self._headers(),
            )
        except httpx.HTTPStatusError as e:
            print(
                f"Update progress failed for ({status}, {message}, {details}): "
                f"({e.response.status_code}) {e.response.text}"
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"Update progress failed for ({status}, {message}, {details}): "
                f"{e.__class__.__name__} {e}"
            )
