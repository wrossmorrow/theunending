import base64
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
) -> None:
    _ = _request_with_retry(
        method="PUT", 
        url=url, 
        client=client,
        json={
            "status": status,
            "message": message,
            "details": details,
        }
    )


def _create_basic_auth_header(credentials: str) -> str:
    return base64.b64encode(credentials.encode("utf-8")).decode("utf-8")


class AdminAPI:

    def __init__(
        self,
        url: str | None,
        auth_secret_name: str | None,
        auth_secret_type: str | None,
        admin_run_id: str | None,
    ) -> None:
        self._url = url
        if url is None:
            return

        headers = {
            "content-type": "application/json",
            "accept": "application/json",
        }
        if auth_secret_type is None:
            auth_secret_type = "Bearer"
        if auth_secret_name is not None:
            auth_secret = os.environ[auth_secret_name]
            if auth_secret_type == "Bearer":
                headers["authorization"] = f"{auth_secret_type} {auth_secret}"
            elif auth_secret_type == "Basic":
                auth_secret = _create_basic_auth_header(auth_secret)
                headers["authorization"] = f"{auth_secret_type} {auth_secret}"
            else:
                raise ValueError(f"Unsupported auth_secret_type '{auth_secret_type}'")

        if admin_run_id is not None:
            headers["x-admin-run-id"] = admin_run_id
    
        self._http = httpx.Client(headers=headers)

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
        
        return _update_progress(
            client=self._http,
            url=self._url,
            status=status,
            message=message,
            details=details,
        )
