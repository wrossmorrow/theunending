import hashlib
import os

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.exceptions import HTTPException as StarletteHTTPException

import modal

DEFAULT_S3_BUCKET_NAME = "wrossmorrow-genai-repetitions-use1"
AUTH_TOKEN_HEADER_NAME = "MODAL_ENDPOINT_AUTH_TOKEN"

MODAL_APP_NAME = "theunending"


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

    if "prompt" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload sent must have 'prompt'",
        )

    prompt = payload["prompt"]

    target = modal.Function.from_name(MODAL_APP_NAME, "evaluate")
    
    hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    bucket = payload.get("s3_bucket", DEFAULT_S3_BUCKET_NAME)
    prefix = payload["s3_prefix"] if "s3_prefix" in payload else f"drafts/{hash}"
    fcall = target.spawn({
        "kwargs": {
            "s3_bucket": bucket,
            "s3_prefix": prefix,
            "prompt": prompt,
        },
    })
    
    return {
        "message": "Successfully launched target app function!",
        "details": {
            "prompt": prompt,
            "prompt_hash": hash,
            "destination_bucket": bucket,
            "destination_prefix": prefix,
            "modal_app_name": MODAL_APP_NAME,
            "modal_app_function": "evaluate",
            "modal_id": fcall.object_id,
        }
    }


@api.post("/batch")
def _batch(payload: dict, authed: bool = Depends(_check_auth)):
  
    if "prompt" not in payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload sent must have 'prompt'",
        )

    prompt = payload["prompt"]

    target = modal.Function.from_name(MODAL_APP_NAME, "batch")
    
    hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    bucket = payload.get("s3_bucket", DEFAULT_S3_BUCKET_NAME)
    prefix = payload["s3_prefix"] if "s3_prefix" in payload else f"runs/{hash}"
    fcall = target.spawn({
        "flags": (
            "embed",
        ),
        "kwargs": {
            "s3_bucket": bucket,
            "s3_prefix": prefix,
            "prompt": prompt,
            "max_images": payload.get("max_images", 5000),
        }
    })
    
    return {
        "message": "Successfully launched target app function!",
        "details": {
            "prompt": prompt,
            "prompt_hash": hash,
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
