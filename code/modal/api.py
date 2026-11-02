import hashlib
import os

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import modal

DEFAULT_MODEL = "black-forest-labs/FLUX.2-klein-4B"
DEFAULT_S3_BUCKET_NAME = "wrossmorrow-genai-repetitions-use1"
AUTH_TOKEN_HEADER_NAME = "MODAL_ENDPOINT_AUTH_TOKEN"
MODAL_APP_NAME = "theunending"


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
    status_update_auth_secret_name: str = "ADMIN_API_TOKEN"
    status_update_auth_secret_type: str = "Bearer"

    def hash(self) -> str:
        return _compute_model_prompt_hash(self.model, self.prompt)


api = FastAPI()
auth_scheme = HTTPBearer()


def _check_auth(request: Request, token: HTTPAuthorizationCredentials = Depends(auth_scheme)) -> bool:
    if token.credentials != os.environ[AUTH_TOKEN_HEADER_NAME]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


def _parse_prompt(payload: dict) -> str:

    if "prompt" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload sent must have 'prompt'",
        )

    prompt = payload["prompt"]

    if len(prompt) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt too short",
        )
    
    if len(prompt) > 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt too long",
        )

    return prompt


@api.exception_handler(Exception)
async def _exception_handler(request: Request, exc: Exception):
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
def _evaluate(payload: JobParameters, authed: bool = Depends(_check_auth)):
    target = modal.Function.from_name(MODAL_APP_NAME, "evaluate")
    kwargs = payload.model_dump(mode="json")
    fcall = target.spawn({"kwargs": kwargs})
    return {
        "external_run_id": fcall.object_id,
        "message": "Successfully launched target app function!",
        "details": {
            "parameters": payload.model_dump(mode="json"),
            "modal_app_name": MODAL_APP_NAME,
            "modal_app_function": "evaluate",
            "modal_id": fcall.object_id,
        }
    }


@api.post("/batch")
def _batch(payload: JobParameters, authed: bool = Depends(_check_auth)):
    target = modal.Function.from_name(MODAL_APP_NAME, "batch")
    kwargs = payload.model_dump(mode="json")
    fcall = target.spawn({"flags": ("embed",), "kwargs": kwargs})
    return {
        "external_run_id": fcall.object_id,
        "message": "Successfully launched target app function!",
        "details": {
            "parameters": kwargs,
            "modal_app_name": MODAL_APP_NAME,
            "modal_app_function": "batch",
            "modal_id": fcall.object_id,
        }
    }


@api.post("/embed")
def _embed(authed: bool = Depends(_check_auth)):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED)


image = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]")

app = modal.App("theunending-api")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("theunending-auth-token")]
)
@modal.asgi_app()
def entrypoint():
    return api
