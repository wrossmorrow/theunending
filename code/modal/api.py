import hashlib
import os

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException

import modal

DEFAULT_MODEL = "black-forest-labs/FLUX.2-klein-4B"
DEFAULT_S3_BUCKET_NAME = "wrossmorrow-genai-repetitions-use1"
AUTH_TOKEN_HEADER_NAME = "MODAL_ENDPOINT_AUTH_TOKEN"

MODAL_APP_NAME = "theunending"


api = FastAPI()
auth_scheme = HTTPBearer()



def _compute_model_prompt_hash(model: str, prompt: str) -> str:
    """Compute the model prompt hash: sha256(model::prompt)."""
    return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()


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
def _evaluate(payload: dict, authed: bool = Depends(_check_auth)):

    prompt = _parse_prompt(payload)
    model = payload.get("model", DEFAULT_MODEL)
    bucket = payload.get("s3_bucket", DEFAULT_S3_BUCKET_NAME)
    hash = _compute_model_prompt_hash(model, prompt)
    prefix = payload["s3_prefix"] if "s3_prefix" in payload else f"drafts/{hash}"
    run_id = payload.get("run_id")
    update_url = payload.get("update_url")

    kwargs = {
        "s3_bucket": bucket,
        "s3_prefix": prefix,
        "prompt": prompt,
        "status_update_url": update_url,
        "status_update_auth_secret_name": "ADMIN_API_TOKEN",
        "status_update_auth_secret_type": "Bearer",
        "status_update_admin_run_id": run_id,
    }

    target = modal.Function.from_name(MODAL_APP_NAME, "evaluate")
    fcall = target.spawn({"kwargs": kwargs})
    
    return {
        "message": "Successfully launched target app function!",
        "details": {
            "prompt": prompt,
            "model_prompt_hash": hash,
            "destination_bucket": bucket,
            "destination_prefix": prefix,
            "modal_app_name": MODAL_APP_NAME,
            "modal_app_function": "evaluate",
            "modal_id": fcall.object_id,
        }
    }


@api.post("/batch")
def _batch(payload: dict, authed: bool = Depends(_check_auth)):

    prompt = _parse_prompt(payload)
    model = payload.get("model", DEFAULT_MODEL)
    bucket = payload.get("s3_bucket", DEFAULT_S3_BUCKET_NAME)
    hash = _compute_model_prompt_hash(model, prompt)
    prefix = payload["s3_prefix"] if "s3_prefix" in payload else f"runs/{hash}"
    run_id = payload.get("run_id")
    update_url = payload.get("update_url")
    
    flags = (
        "embed",
    )
    kwargs = {
        "s3_bucket": bucket,
        "s3_prefix": prefix,
        "prompt": prompt,
        "max_images": payload.get("max_images", 5000),
        "status_update_url": update_url,
        "status_update_auth_secret_name": "ADMIN_API_TOKEN",
        "status_update_auth_secret_type": "Bearer",
        "status_update_admin_run_id": run_id,
    }
    
    target = modal.Function.from_name(MODAL_APP_NAME, "batch")
    fcall = target.spawn({
        "flags": flags,
        "kwargs": kwargs,
    })
    
    return {
        "message": "Successfully launched target app function!",
        "details": {
            "prompt": prompt,
            "model_prompt_hash": hash,
            "destination_bucket": bucket,
            "destination_prefix": prefix,
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
