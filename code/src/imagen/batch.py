from __future__ import annotations

import argparse
import inspect
import io
import os
import random
import threading
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import boto3
import numpy as np
import torch
from PIL import Image

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from .constants import DEVICE
from .pipeline import load_pipeline
from .progress import AdminAPI, Status
from .similarity.embed import command as embed_command
from .similarity.embed import handle as embed

MAX_PENDING = int(os.environ.get("MAX_PENDING", "16"))
UPLOAD_OS_THREADS = int(os.environ.get("UPLOAD_OS_THREADS", "8"))

# Images that fail the generated-image checks are persisted apart from accepted
# ones (under this subdirectory) so they can be inspected without ever entering
# the generated set that gets embedded/published.
REJECTED_DIRNAME = "rejected"

# A pixel counts as "solid black" when its brightest channel is at/below this
# value (0-255). Pure black letterbox bars land at/near zero; legitimately dark
# imagery still registers above it, so whole-image darkness is not itself a
# rejection reason.
SOLID_BLACK_MAX_CHANNEL = 16


_slots = threading.Semaphore(MAX_PENDING)
_failures: list[Any] = []  # really Exception of BaseException
_rejections: list[dict[str, Any]] = []
_rejection_metrics: dict[str, int] = {}
_lock = threading.Lock()


upload_pool = ThreadPoolExecutor(max_workers=UPLOAD_OS_THREADS)
progress_pool = ThreadPoolExecutor(max_workers=1)


def count_s3_prefix_objects(
    s3: S3Client,
    bucket: str,
    prefix: str,
    suffix: str | Sequence[str] | None = ".png",
    exclude_prefixes: Sequence[str] = (),
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
            total_count += sum(
                1
                for obj in contents
                if obj["Key"].endswith(suffix)
                and not any(obj["Key"].startswith(p) for p in exclude_prefixes)
            )

    return total_count


def check_image(image: Image.Image) -> str | None:
    """Return why a generated image should be rejected, or None if it is acceptable.

    Generated images can come back letterboxed, with solid black bars filling
    the unused frame area. Those bars are indistinguishable from legitimately
    dark imagery when judged by overall brightness, so bars are detected as rows
    and columns that carry no content at all (fully solid black).
    """
    max_channel = np.asarray(image.convert("RGB"), dtype=np.float32).max(axis=2)
    content = max_channel > SOLID_BLACK_MAX_CHANNEL

    if not content.any():
        # No content at all: an entirely black frame is not a usable image.
        return "all-black"

    if not content.any(axis=1).all() or not content.any(axis=0).all():
        # Some row/column is entirely solid black: a letterbox bar (top/bottom
        # or left/right), or a degenerate frame.
        return "letterboxed"

    return None


def record_rejection(reason: str, seed: int, prompt: str, index: int) -> None:
    with _lock:
        _rejection_metrics[reason] = _rejection_metrics.get(reason, 0) + 1
        _rejections.append(
            {
                "index": index,
                "seed": seed,
                "prompt": prompt,
                "reason": reason,
            }
        )

    print(
        f"Rejected image {index}: reason={reason} seed={seed} prompt={prompt[:60]!r}",
        flush=True,
    )


def save_image_and_upload(
    image,
    format: str,
    outdir: str,
    s3_bucket: str,
    s3_prefix: str,
    metadata: dict,
    s3: S3Client,
    rejected_reason: str | None = None,
) -> None:

    ext = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[format.upper()]

    buf = io.BytesIO()
    image.save(buf, format=format.upper(), optimize=True)
    raw_bytes = buf.getvalue()

    image_id = uuid4()
    if rejected_reason is None:
        filename = Path(outdir) / f"{image_id}.{ext}"
        s3_key = f"{s3_prefix}/{image_id}.{ext}"
    else:
        filename = Path(outdir) / REJECTED_DIRNAME / f"{image_id}.{ext}"
        s3_key = f"{s3_prefix}/rejected/{image_id}.{ext}"

    tmp = filename.with_suffix(".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(raw_bytes)
    os.replace(tmp, filename)  # atomic on the same filesystem

    full_metadata = dict(metadata)
    if rejected_reason is not None:
        full_metadata["rejected"] = "true"
        full_metadata["reason"] = rejected_reason

    s3.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=raw_bytes,
        ContentType=f"image/{format.lower()}",
        Metadata={
            k: v.encode("ascii", "ignore").decode() for k, v in full_metadata.items()
        },
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
    upload_pool.submit(save_image_and_upload, *a).add_done_callback(_done)


def handle(
    args: argparse.Namespace,
    s3: S3Client | None,
) -> int:

    if s3 is None:
        return handle(args, boto3.client("s3"))

    admin_api = AdminAPI(
        url=args.status_update_url,
        auth_secret_name=args.status_update_auth_secret_name,
        auth_secret_type=args.status_update_auth_secret_type,
        admin_run_id=args.status_update_admin_run_id,
    )

    try:
        admin_api.update_progress(
            status=Status.IN_PROGRESS,
            message="job has launched successfully",
        )

        os.makedirs(args.outdir, exist_ok=True)

        existing = count_s3_prefix_objects(
            s3,
            args.s3_bucket,
            args.s3_prefix,
            exclude_prefixes=(f"{args.s3_prefix}rejected/",),
        )
        total = args.max_images - existing

        print(f"Progress: {existing}/{args.max_images} already exist; work on {total}.")

        admin_api.update_progress(
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

            reject_reason = check_image(image)

            if reject_reason is None:
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
            else:
                record_rejection(reject_reason, seed, chopped_prompt, idx)
                submit_upload(
                    image,
                    args.format,
                    args.outdir,
                    args.s3_bucket,
                    args.s3_prefix,
                    {
                        "seed": str(seed),
                        "prompt": chopped_prompt,
                        "rejected": "true",
                        "reason": reject_reason,
                    },
                    s3,
                    rejected_reason=reject_reason,
                )

            if (idx + 1) % 50 == 0 or (idx + 1) == total:
                message = f"Progress: [{idx + 1}/{total}] generated and queued."
                print(message)
                progress_pool.submit(
                    admin_api.update_progress,
                    status=Status.IN_PROGRESS,
                    message=message,
                )

        upload_pool.shutdown(wait=True)
        progress_pool.shutdown(wait=True)

        with _lock:
            rejection_metrics = dict(_rejection_metrics)
            rejections = list(_rejections)

        print(
            f"Generated {total} image(s) for prompt {chopped_prompt!r}: "
            f"accepted {total - len(rejections)}, rejected {len(rejections)} "
            f"(reasons: {rejection_metrics or 'none'})"
        )

        if _failures:
            message = f"FAILED: {len(_failures)} uploads did not complete"
            print(message)
            admin_api.update_progress(
                status=Status.FAILED,
                message=message,
            )
            return 1

        print("All tasks finished and synced to S3.")
        if not args.embed:
            admin_api.update_progress(
                status=Status.COMPLETED,
                message="work completed successfully",
                details={"rejected": rejection_metrics},
            )

            return 0

        admin_api.update_progress(
            status=Status.IN_PROGRESS,
            message="image generation and s3 upload completed",
        )

        print("Starting embedding on local images.")
        del pipe
        embed_parser = embed_command(argparse.ArgumentParser())
        embed_argv = [
            args.outdir,
            "--device",
            DEVICE,
            "--s3-bucket",
            args.s3_bucket,
            "--s3-prefix",
            args.s3_prefix,
            "--no-recursive",
        ]
        embed_args = embed_parser.parse_args(embed_argv)
        embed(embed_args, s3)
        print("Finished embedding and synced to S3.")

        admin_api.update_progress(
            status=Status.COMPLETED,
            message="image generation, s3 upload, and embeddings completed",
            details={"rejected": rejection_metrics},
        )

    except Exception as e:  # noqa: BLE001
        frame = inspect.currentframe()
        fname = frame.f_code.co_name if frame is not None else "<unknown>"
        print(f"An error occurred in {fname}: {e.__class__.__name__} {e}")
        admin_api.update_progress(
            status=Status.FAILED,
            message="An uncaught error occurred during processing",
            details={
                "function_name": fname,
                "error": str(e),
                "error_class": e.__class__.__name__,
                "args": {k: v for k, v in vars(args).items()},
            },
        )

        return 1

    return 0


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument(
        "--s3-bucket", type=str, default=os.environ.get("AWS_S3_BUCKET_NAME")
    )
    parser.add_argument("--s3-prefix", type=str, required=True)
    parser.add_argument("--max-images", type=int, default=5_000)
    parser.add_argument(
        "--format", type=str, default="PNG", choices=["PNG", "JPEG", "WEBP"]
    )
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--outdir", type=str, default="images")
    parser.add_argument(
        "--model-id", type=str, default="black-forest-labs/FLUX.2-klein-4B"
    )
    parser.add_argument("--embed", action="store_true", default=False)
    parser.add_argument(
        "--status-update-url",
        type=str,
        default=None,
        help="An explicit URL to issue PUT calls for status updates; ignored if empty",
    )
    parser.add_argument(
        "--status-update-auth-secret-name",
        type=str,
        default=None,
        help="Status update auth secret name; ignored if empty",
    )
    parser.add_argument(
        "--status-update-auth-secret-type",
        type=str,
        default=None,
        help="Status update auth secret type (Bearer, Basic); ignored if empty",
    )
    parser.add_argument(
        "--status-update-admin-run-id",
        type=str,
        default=None,
        help="An explicit 'run_id' for correlation to admin systems; ignored if empty",
    )
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main() -> None:
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
