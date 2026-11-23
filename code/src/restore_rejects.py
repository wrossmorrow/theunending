# /// script
# requires-python = ">=3.10"
# dependencies = ["boto3"]
# ///
"""
Count accepted images in a run prefix and move randomly chosen rejects back
into it, until the run has --target images (or exactly --count moved).

    uv run restore_rejects.py --bucket B --prefix runs/<hash>              # dry run
    uv run restore_rejects.py --bucket B --prefix runs/<hash> --apply
    uv run restore_rejects.py --bucket B --prefix runs/<hash> --count 50 --seed 7 --apply

Accepted = <prefix>/*.png (top level only); rejected = <prefix>/rejected/*.png.
Moves are copy + delete, and drop the rejected/reason metadata on the copy.
"""
from __future__ import annotations

import argparse
import random
import sys

import boto3


def list_keys(s3, bucket: str, prefix: str, ext: str) -> list[str]:
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix=prefix, Delimiter="/"  # top level only
    ):
        keys += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(ext)]
    return keys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", required=True, help="run prefix, e.g. runs/<hash>")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--target", type=int, default=5000, help="fill accepted up to this many (default 5000)")
    g.add_argument("--count", type=int, help="move exactly this many instead")
    ap.add_argument("--ext", default=".png")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--apply", action="store_true", help="actually move (default: dry run)")
    args = ap.parse_args()

    s3 = boto3.client("s3")
    prefix = args.prefix.rstrip("/") + "/"
    rej_prefix = prefix + "rejected/"

    accepted = list_keys(s3, args.bucket, prefix, args.ext)
    rejected = list_keys(s3, args.bucket, rej_prefix, args.ext)
    print(f"accepted: {len(accepted)}   rejected: {len(rejected)}")

    want = args.count if args.count is not None else max(args.target - len(accepted), 0)
    if want == 0:
        print("nothing to move")
        return 0
    if want > len(rejected):
        print(f"need {want} but only {len(rejected)} rejected available", file=sys.stderr)
        return 1

    picks = random.Random(args.seed).sample(rejected, want)
    print(f"{'moving' if args.apply else 'would move'} {want} -> {prefix}")

    for i, src in enumerate(picks, 1):
        dst = prefix + src[len(rej_prefix):]
        if not args.apply:
            if i <= 5:
                print(f"  {src} -> {dst}")
            continue
        head = s3.head_object(Bucket=args.bucket, Key=src)
        meta = {k: v for k, v in head.get("Metadata", {}).items() if k not in ("rejected", "reason")}
        s3.copy_object(
            Bucket=args.bucket,
            Key=dst,
            CopySource={"Bucket": args.bucket, "Key": src},
            Metadata=meta,
            MetadataDirective="REPLACE",
            ContentType=head.get("ContentType", "image/png"),
        )
        s3.delete_object(Bucket=args.bucket, Key=src)
        if i % 50 == 0 or i == want:
            print(f"  moved {i}/{want}")

    if not args.apply and want > 5:
        print(f"  ... and {want - 5} more (dry run; pass --apply)")
    print(f"accepted after: {len(accepted) + (want if args.apply else 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
