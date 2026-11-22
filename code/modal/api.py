import hashlib
import os
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import modal

DEFAULT_MODEL = "black-forest-labs/FLUX.2-klein-4B"
DEFAULT_S3_BUCKET_NAME = "theunending-ai-raw-content-use1"
DEFAULT_ADMIN_API_AUDIENCE = "https://admin.theunending.ai"
MODAL_APP_NAME = "theunending"

# Machine auth (see code/src/machine_auth/__init__.py): the endpoint accepts a fresh
# RS256 JWT minted by the admin service account and verified against Google's
# per-account JWKS endpoint. The expected issuer comes from the modal secret
# "google-machine" (GOOGLE_SERVICE_ACCOUNT_EMAIL); key rotation is handled by
# Google, so Envoy/Modal need no redeploy on rotation.
EXPECTED_ISSUER_ENV = "GOOGLE_SERVICE_ACCOUNT_EMAIL"
AUDIENCE_ENV = "ADMIN_API_AUDIENCE"
JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/{email}"


def _expected_audience() -> str:
    return (os.environ.get(AUDIENCE_ENV) or "").strip() or DEFAULT_ADMIN_API_AUDIENCE


def _expected_issuer() -> str:
    return (os.environ.get(EXPECTED_ISSUER_ENV) or "").strip()


def _jwk_client() -> jwt.PyJWKClient:
    """Client for the Google per-account JWKS endpoint (cached)."""
    email = _expected_issuer()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="machine JWT issuer is not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return jwt.PyJWKClient(JWKS_URL.format(email=email), cache_keys=True, lifespan=300)


def _compute_model_prompt_hash(model: str, prompt: str) -> str:
    """Compute the model prompt hash: sha256(model::prompt)."""
    return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()


class JobParameters(BaseModel):
    """Parameters for an external job creation request."""

    model_id: str = DEFAULT_MODEL
    s3_bucket: str = DEFAULT_S3_BUCKET_NAME
    s3_prefix: str = Field(min_length=1, max_length=1024)
    prompt: str = Field(min_length=1, max_length=1024)
    status_update_url: str | None = None
    status_update_admin_run_id: str | None = None
    ignore_reject: bool = False

    def hash(self) -> str:
        return _compute_model_prompt_hash(self.model_id, self.prompt)


class CancelParameters(BaseModel):
    """Parameters for an external job cancellation request."""

    external_run_id: str
    job_type: Literal["EVALUATE", "BATCH", "EMBED"]


api = FastAPI()
auth_scheme = HTTPBearer()


def _check_auth(
    request: Request,
    token: HTTPAuthorizationCredentials = Depends(auth_scheme),  # noqa: B008 - FastAPI dependency injection idiom
) -> bool:
    expected_iss = _expected_issuer()
    if not expected_iss:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="machine JWT issuer is not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        signing_key = _jwk_client().get_signing_key_from_jwt(token.credentials)
        payload = jwt.decode(
            token.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=_expected_audience(),
            issuer=expected_iss,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid machine token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    sub = payload.get("sub")
    if sub != expected_iss:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid machine token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


@api.exception_handler(Exception)
async def _exception_handler(request: Request, exc: Exception) -> JSONResponse:

    print(
        f"Caught unhandled exception for {request.method} {request.url}: {exc.__class__.__name__} {exc}"
    )

    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        raise exc

    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "error_class": exc.__class__.__name__,
        },
    )


@api.post("/evaluate")
def _evaluate(
    payload: JobParameters, request: Request, authed: bool = Depends(_check_auth)
):

    print(
        f"Received {request.method} {request.url} with params: {payload.model_dump_json()}"
    )

    target = modal.Function.from_name(MODAL_APP_NAME, "evaluate")
    kwargs = payload.model_dump(mode="json")
    kwargs.pop("ignore_reject", None)
    fcall = target.spawn({"kwargs": kwargs})
    return {
        "external_run_id": fcall.object_id,
        "message": "Successfully launched target app function!",
        "details": {
            "parameters": payload.model_dump(mode="json"),
            "modal_app_name": MODAL_APP_NAME,
            "modal_app_function": "evaluate",
            "modal_id": fcall.object_id,
        },
    }


@api.post("/batch")
def _batch(
    payload: JobParameters, request: Request, authed: bool = Depends(_check_auth)
):

    print(
        f"Received {request.method} {request.url} with params: {payload.model_dump_json()}"
    )

    target = modal.Function.from_name(MODAL_APP_NAME, "batch")
    kwargs = payload.model_dump(mode="json")
    ignore_reject = bool(kwargs.pop("ignore_reject", False))
    flags: tuple[str, ...] = ("embed",)
    if ignore_reject:
        flags = ("embed", "ignore_reject")
    fcall = target.spawn({"flags": flags, "kwargs": kwargs})
    return {
        "external_run_id": fcall.object_id,
        "message": "Successfully launched target app function!",
        "details": {
            "parameters": kwargs,
            "modal_app_name": MODAL_APP_NAME,
            "modal_app_function": "batch",
            "modal_id": fcall.object_id,
        },
    }


@api.post("/embed")
def _embed(authed: bool = Depends(_check_auth)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


@api.post("/cancel")
def _cancel(
    payload: CancelParameters, request: Request, authed: bool = Depends(_check_auth)
):

    print(
        f"Received {request.method} {request.url} with params: {payload.model_dump_json()}"
    )

    external_run_id = payload.external_run_id

    try:
        fc: modal.functions.FunctionCall = modal.FunctionCall.from_id(external_run_id)

        # reading the implementation in _FunctionCall suggests this returns nothing
        # need more info though, not sure I understand; may need to get status
        fc.cancel()
        return {
            "status": "CANCELLED",
            "run_id": external_run_id,
        }
    except Exception as e:  # noqa: BLE001 - report any downstream failure as a 500
        print(f"Failed to cancel {external_run_id}: {e.__class__.__name__} {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{e.__class__.__name__} {e}",
        )


image = modal.Image.debian_slim(python_version="3.12").pip_install(
    "fastapi[standard]", "pyjwt", "cryptography"
)

app = modal.App("theunending-api")


@app.function(image=image, secrets=[modal.Secret.from_name("google-machine")])
@modal.asgi_app()
def entrypoint():
    return api
