from __future__ import annotations

import argparse
import inspect
import io
import os
import random
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import boto3
import torch
from diffusers import Flux2KleinPipeline, FluxPipeline

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from .constants import DEVICE, TORCH_DTYPE
from .progress import Status, update_progress
from .similarity.embed import command as embed_command
from .similarity.embed import handle as embed

MAX_PENDING = int(os.environ.get("MAX_PENDING", "16"))
UPLOAD_OS_THREADS = int(os.environ.get("UPLOAD_OS_THREADS", "8"))


_slots = threading.Semaphore(MAX_PENDING)
_failures: list[Any] = []  # really Exception of BaseException
_lock = threading.Lock()


pool = ThreadPoolExecutor(max_workers=UPLOAD_OS_THREADS)


def load_pipeline(model_id) -> Callable:
    pipe = (
        FluxPipeline.from_pretrained(
            model_id,
            torch_dtype=TORCH_DTYPE,
        )
        if "FLUX.1" in model_id else
        Flux2KleinPipeline.from_pretrained(
            model_id,
            torch_dtype=TORCH_DTYPE,
        )
    ).to(DEVICE)
    return pipe


def count_s3_prefix_objects(
    s3: S3Client,
    bucket: str,
    prefix: str,
    suffix: str | Sequence[str] | None = ".png",
) -> int:
    
    # Ensure prefix ends with a slash if targeting a "folder"
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    # Normalize suffix into a tuple so str.endswith() can check single or multiple extensions
    if isinstance(suffix, str):
        suffix = (suffix,)
    elif suffix is not None:
        suffix = tuple(suffix)

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    total_count = 0
    for page in pages:
        if suffix is None:
            total_count += page.get("KeyCount", 0)
        else:
            contents = page.get("Contents", [])
            total_count += sum(1 for obj in contents if obj["Key"].endswith(suffix))

    return total_count


def save_image_and_upload(
    image, 
    format: str, 
    outdir: str,
    s3_bucket: str,
    s3_prefix: str,
    metadata: dict,
    s3: S3Client,
) -> None:

    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[format.upper()]

    buf = io.BytesIO()
    image.save(buf, format=format.upper(), optimize=True)
    raw_bytes = buf.getvalue()

    image_id = uuid4()
    filename = Path(outdir) / f"{image_id}.{ext}"
    s3_key = f"{s3_prefix}/{image_id}.{ext}"

    tmp = filename.with_suffix(".tmp")
    tmp.write_bytes(raw_bytes)
    os.replace(tmp, filename)      # atomic on the same filesystem

    s3.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=raw_bytes,
        ContentType=f"image/{format.lower()}",
        Metadata={k: v.encode("ascii", "ignore").decode() for k, v in metadata.items()},
    )


def _done(fut) -> None:
    _slots.release()
    exc = fut.exception()
    if exc:
        with _lock:
            _failures.append(exc)
        print(f"  upload failed: {exc!r}", flush=True)


def submit_upload(*a) -> None:
    _slots.acquire()
    pool.submit(save_image_and_upload, *a).add_done_callback(_done)


def handle(
    args: argparse.Namespace,
    s3: S3Client | None,
) -> int:

    if s3 is None:
        return handle(args, boto3.client("s3"))

    try:

        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.IN_PROGRESS,
                message="job has launched successfully",
            )

        os.makedirs(args.outdir, exist_ok=True)

        existing = count_s3_prefix_objects(s3, args.s3_bucket, args.s3_prefix)
        total = args.max_images - existing

        print(f"Progress: {existing}/{args.max_images} already exist; work on {total}.")

        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.IN_PROGRESS,
                message=f"working on {total}/{args.max_images} images",
            )

        pipe = load_pipeline(args.model_id)

        chopped_prompt = args.prompt[:120]

        for idx in range(total):

            seed = random.randint(0, 2**32 - 1)

            gen = torch.Generator(device=DEVICE).manual_seed(seed)
            image = pipe(
                prompt=args.prompt,
                num_inference_steps=args.steps,
                generator=gen,
                height=args.height,
                width=args.width,
            ).images[0]

            submit_upload(
                image,
                args.format,
                args.outdir,
                args.s3_bucket,
                args.s3_prefix,
                {
                    "seed": str(seed),
                    "prompt": chopped_prompt,
                },
                s3,
            )

            if (idx + 1) % 50 == 0 or (idx + 1) == total:
                message = f"Progress: [{idx + 1}/{total}] generated and queued."
                print(message)
                if args.status_update_url is not None:
                    update_progress(
                        url=args.status_update_url,
                        status=Status.IN_PROGRESS,
                        message=message,
                    )

        pool.shutdown(wait=True)

        if _failures:
            message = f"FAILED: {len(_failures)} uploads did not complete"
            print(message)
            if args.status_update_url is not None:
                update_progress(
                    url=args.status_update_url,
                    status=Status.FAILED,
                    message=message,
                )
            return 1
        
        print("All tasks finished and synced to S3.")
        if not args.embed:
            if args.status_update_url is not None:
                update_progress(
                    url=args.status_update_url,
                    status=Status.COMPLETED,
                    message="work completed successfully",
                )
            
            return 0

        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.IN_PROGRESS,
                message="image generation and s3 upload completed",
            )
        
        print("Starting embedding on local images.")
        del pipe
        embed_parser = embed_command(argparse.ArgumentParser())
        embed_argv = [
            args.outdir,
            "--device", DEVICE,
            "--s3-bucket", args.s3_bucket,
            "--s3-prefix", args.s3_prefix,
        ]
        embed_args = embed_parser.parse_args(embed_argv)
        embed(embed_args, s3)
        print("Finished embedding and synced to S3.")

        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.COMPLETED,
                message="image generation, s3 upload, and embeddings completed",
            )

    except Exception as e:  # noqa: BLE001
        frame = inspect.currentframe()
        fname = frame.f_code.co_name if frame is not None else "<unknown>"
        print(f"An error occurred in {fname}: {e.__class__.__name__} {e}")
        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.FAILED,
                message="An uncaught error occurred during processing",
                details={
                    "function_name": fname,
                    "error": str(e),
                    "error_class": e.__class__.__name__,
                    "args": {k: v for k, v in vars(args).items()}
                }
            )

        return 1

    return 0
            

def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--s3-bucket", type=str, default=os.environ.get("AWS_S3_BUCKET_NAME"))
    parser.add_argument("--s3-prefix", type=str, required=True)
    parser.add_argument("--max-images", type=int, default=5_000)
    parser.add_argument("--format", type=str, default="PNG", choices=["PNG", "JPEG", "WEBP"])
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--outdir", type=str, default="images")
    parser.add_argument("--model-id", type=str, default="black-forest-labs/FLUX.2-klein-4B")
    parser.add_argument("--embed", action="store_true", default=False)
    parser.add_argument("--status-update-url", type=str, default=None)
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main() -> None:
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
