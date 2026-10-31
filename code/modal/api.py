import hashlib

from fastapi import HTTPException, status
import modal

image = modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]")

app = modal.App("theunending-api")

# @app.function(image=image)
# @modal.fastapi_endpoint()
# def f():

#     try:
#         # Fetch and list all active handles for live Apps
#         values = {
#             app.name: app.app_id 
#             for app in modal.Environment.from_name("main").apps.list()
#         }
#         return f"Hello world! {values}"
#     except Exception as e:
#         return f"Oops: {e.__class__.__name__} {e}"


@app.function(image=image)
@modal.fastapi_endpoint(
    method="POST",
    label="evaluate",
)
def evaluate_handler(payload: dict):

    if "prompt" not in payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)

    prompt = payload["prompt"]

    # 1. Look up the deployed target function by its App name and Function name
    target = modal.Function.from_name("theunending", "evaluate")
    
    # 2. Trigger the target function
    # Use .spawn() to trigger it in the background and return immediately
    hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    target.spawn({
        "s3_bucket": "wrossmorrow-genai-repetitions-use1",
        "s3_prefix": f"drafts/{hash}",
        "prompt": prompt,
    })
    
    # Or use .remote() if you need to wait for and return its result:
    # result = target_func.remote(data=...)

    return {
        "message": "Successfully launched target app function!",
        "details": {
            "prompt": prompt,
            "prompt_hash": hash,
        }
    }
