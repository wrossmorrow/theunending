# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "pyyaml", "boto3"]
# ///
"""
Make one small WebP per set for the index: the `thumb:` id of each set in
_data/streams.yml, downscaled to assets/img/index-thumbs/<id>.webp.

Files are named by image id, so changing a set's `thumb:` makes a new file
on the next run instead of silently reusing the old one. Existing outputs
are skipped unless --force.

Source is the site bucket by default, at the key the set's `base:` URL
points to (https://theunending.ai/assets/img/<dir>/ -> assets/img/<dir>/).
With --src-dir, reads <src-dir>/<dir>/<id>.png from a local store instead.

    uv run scripts/make-index-thumbs.py
    uv run scripts/make-index-thumbs.py --src-dir ~/path/to/raw --force
    uv run scripts/make-index-thumbs.py --only easy-out --only poltergeist
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from PIL import Image

BUCKET = "theunending-ai-site-content-use1"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="_data/streams.yml")
    ap.add_argument("--out", default="assets/img/index-thumbs")
    ap.add_argument("--size", type=int, default=640, help="longest edge in px (default 640: 2x a ~320px tile)")
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--bucket", default=BUCKET)
    ap.add_argument("--src-dir", type=Path, help="read from a local store laid out <dir>/<id>.png instead of S3")
    ap.add_argument("--only", action="append", help="limit to these set keys (repeatable)")
    ap.add_argument("--force", action="store_true", help="rebuild outputs that already exist")
    args = ap.parse_args()

    data = yaml.safe_load(Path(args.data).read_text()) or {}
    sets = data.get("sets") or {}
    defaults = data.get("defaults") or {}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    s3 = None
    if not args.src_dir:
        import boto3
        s3 = boto3.client("s3")

    made = skipped = failed = 0
    for key, cfg in sets.items():
        if args.only and key not in args.only:
            continue
        tid = cfg.get("thumb")
        base = cfg.get("base")
        if not tid or not base:
            print(f"skip   {key}: no thumb or base", file=sys.stderr)
            continue
        dst = out / f"{tid}.webp"
        if dst.exists() and not args.force:
            skipped += 1
            continue

        ext = "." + str(cfg.get("ext") or defaults.get("ext") or "png").lstrip(".")
        prefix = urlparse(base).path.lstrip("/")          # assets/img/<dir>/
        try:
            if args.src_dir:
                raw = (args.src_dir.expanduser() / Path(prefix).name / f"{tid}{ext}").read_bytes()
            else:
                raw = s3.get_object(Bucket=args.bucket, Key=f"{prefix}{tid}{ext}")["Body"].read()
            im = Image.open(io.BytesIO(raw))
            im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
            im.thumbnail((args.size, args.size), Image.Resampling.LANCZOS)
            tmp = dst.with_suffix(".webp.tmp")
            im.save(tmp, "WEBP", quality=args.quality, method=6)
            tmp.replace(dst)                                # no half-written thumbs
            made += 1
            print(f"made   {key}  {dst}  {dst.stat().st_size // 1024}KB")
        except Exception as e:  # keep going; report at the end
            failed += 1
            print(f"FAIL   {key}  {tid}: {e}", file=sys.stderr)

    print(f"\n{made} made, {skipped} already present, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
