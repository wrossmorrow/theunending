"""Command line interface for local PE Core image embeddings."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import numpy as np

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from .encoder import DEFAULT_MODEL, MODELS, PEEncoder, iter_images


def _sidecar(out: Path) -> Path:
    return out.with_suffix(out.suffix + ".json")


def _progress(done: int, total: int) -> None:
    print(f"\r  embedded {done}/{total}", end="", file=sys.stderr, flush=True)


def _dedup_trailing_slashes(prefix: str) -> str:
    while prefix.endswith("/"):
        if len(prefix) == 0:
            break
        prefix = prefix[:-1]

    return f"{prefix}/" if prefix else ""


def _copy_to_s3(
    out: Path,
    s3_bucket: str | None,
    s3_prefix: str | None,
    s3: S3Client,
) -> None:
    if s3_bucket is None:
        return

    prefix = _dedup_trailing_slashes(f"{s3_prefix}/" if s3_prefix else "")

    s3.upload_file(
        Filename=str(out.resolve()),
        Bucket=s3_bucket,
        Key=f"{prefix}{out.name}",
    )

    sdc = _sidecar(out)
    s3.upload_file(
        Filename=str(sdc.resolve()),
        Bucket=s3_bucket,
        Key=f"{prefix}{sdc.name}",
    )


def _get_ext(format: str) -> str:
    return {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}[format.upper()]


def _list_s3(s3: S3Client, bucket: str, prefix: str, ext: str) -> list[str]:
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith(ext):
                keys.append(obj["Key"])
    keys.sort()
    return keys


def _get_from_s3(
    s3: S3Client,
    s3_bucket: str | None,
    s3_prefix: str | None,
    local_path: str,
    format: str,
) -> None:
    if s3_bucket is None:
        raise ValueError("Cannot source from S3 without a bucket name")

    prefix = _dedup_trailing_slashes(f"{s3_prefix}/" if s3_prefix else "")
    ext = _get_ext(format)
    keys = _list_s3(s3, s3_bucket, prefix, ext)
    for key in keys:
        fn = key.split("/")[-1]
        s3.download_file(
            Bucket=s3_bucket,
            Key=key,
            Filename=f"{local_path}/{fn}",
        )


def handle(args: argparse.Namespace, s3: S3Client) -> int:

    if s3 is None:
        handle(args, boto3.client("s3"))
        return

    # get data from S3 if we've been asked to, store in _first_ path arg
    if args.source_from_s3:
        _get_from_s3(
            s3, 
            args.s3_bucket,
            args.s3_prefix,
            args.format,
            args.paths[0],
        )

    paths = iter_images(args.paths, recursive=(not args.no_recursive))
    if not paths:
        print("No images found.", file=sys.stderr)
        return 1

    path_count = len(paths)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    model = args.model or DEFAULT_MODEL
    print(f"Loading {model} ...", file=sys.stderr)

    started = time.perf_counter()
    encoder = PEEncoder.load(model, device=args.device, dtype=args.dtype)
    print(
        f"  {encoder.model_id} on {encoder.device.type} "
        f"({encoder.image_size}px, {args.dtype}) in {time.perf_counter() - started:.1f}s",
        file=sys.stderr,
    )

    if out.exists():
        E = np.load(str(out))
        if (E.shape[0] == path_count) and (not args.force):
            print(f"Embedding file {out} already exists and appears complete")
            return 0

    started = time.perf_counter()
    vectors = encoder.embed(
        paths,
        batch_size=args.batch_size,
        normalize=not args.no_normalize,
        on_batch=_progress,
    )
    elapsed = time.perf_counter() - started
    print(
        f"\r  embedded {len(paths)}/{len(paths)} in {elapsed:.1f}s "
        f"({elapsed / max(len(paths), 1) * 1000:.0f} ms/image)",
        file=sys.stderr,
    )

    np.save(out, vectors)

    # np.save *appends* .npy when the name lacks it ("v1.dat" -> "v1.dat.npy"),
    # so mirror that rather than replacing the existing suffix.
    saved = out if out.suffix == ".npy" else out.with_name(out.name + ".npy")
    _sidecar(saved).write_text(
        json.dumps(
            {
                "model": encoder.model_id,
                "dim": int(vectors.shape[1]),
                "normalized": not args.no_normalize,
                "paths": [str(p) for p in paths],
            },
            indent=2,
        )
    )
    print(f"Wrote {saved} ({len(paths)} x {vectors.shape[1]}) and {_sidecar(saved)}")

    _copy_to_s3(out, args.s3_bucket, args.s3_prefix, s3)

    return 0


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("paths", nargs="+", help="image files and/or directories")
    parser.add_argument("-o", "--out", default="embeddings.npy", help="output path")
    parser.add_argument("--batch-size", type=int, default=8, help="images per batch [8]")
    parser.add_argument("--format", type=str, default="PNG", help="image format")
    parser.add_argument(
        "--no-normalize", action="store_true", help="skip L2 normalization"
    )
    parser.add_argument(
        "--no-recursive", action="store_true", help="do not descend into subfolders"
    )
    parser.add_argument(
        "--force", action="store_true", help="force recreation if complete detected"
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"short name ({', '.join(MODELS)}) or a hub repo id [{DEFAULT_MODEL}]",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "mps", "cpu", "cuda"],
        help="compute device [auto]",
    )
    parser.add_argument(
        "--dtype",
        default="float32",
        choices=["float32", "float16", "bfloat16"],
        help="model precision [float32]",
    )
    parser.add_argument(
        "--s3-bucket", 
        type=str, 
        default=os.environ.get("AWS_S3_BUCKET_NAME"),
        help="S3 bucket name for upload and potentially sourcing images",
    )
    parser.add_argument(
        "--s3-prefix",
        type=str,
        default="runs/",
        help="S3 prefix for upload and potentially sourcing images",
    )
    parser.add_argument(
        "--source-from-s3",
        action="store_true",
        default=False,
        help="source images from the named s3 paths",
    )
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
