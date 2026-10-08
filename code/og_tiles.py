#!/usr/bin/env python3
"""
Build 1200x630 Open Graph cards by tiling images from a run.

    # one set
    ./og_tiles.py --set computation --prefix runs/run-17 --out assets/og

    # every set listed in a mapping file  (YAML: "set: run" per line, or JSON)
    ./og_tiles.py --map og_runs.yml --out assets/og

    # the site-wide card, sampled across all runs in the map
    ./og_tiles.py --map og_runs.yml --out assets/og --site

    # test the layout without touching S3
    ./og_tiles.py --set demo --source ./some/local/dir --out /tmp/og

Selection is seeded by the set name, so regenerating gives the same card.
That matters: unfurlers cache by URL, so a card that changes every build
means the version people see depends on when they first shared the link.
"""

import argparse
import io
import json
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFont

OG_W, OG_H = 1200, 630

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",      # macOS, matches the site
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",    # linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


# ---------------------------------------------------------------- sources

def list_local(path):
    return sorted(
        os.path.join(path, n) for n in os.listdir(path)
        if n.lower().endswith((".png", ".jpg", ".jpeg"))
    )


def list_s3(bucket, prefix):
    import boto3
    s3 = boto3.client("s3")
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith((".png", ".jpg", ".jpeg")):
                keys.append(obj["Key"])
    keys.sort()
    return keys


def open_local(ref):
    return Image.open(ref)


def open_s3(bucket, key):
    import boto3
    s3 = boto3.client("s3")
    body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return Image.open(io.BytesIO(body))


# ---------------------------------------------------------------- drawing

def square_crop(im, size):
    """Centre-crop to a square, then resize. Sources are already square, but a
    stray non-square render shouldn't skew the grid."""
    w, h = im.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    im = im.crop((left, top, left + side, top + side))
    return im.convert("RGB").resize((size, size), Image.LANCZOS)


def build_card(images, cols, title=None, subtitle=None, gap=0):
    """Tile onto a canvas at least OG_H tall, then centre-crop to 1200x630."""
    tile = (OG_W - gap * (cols - 1)) // cols
    rows = max(1, math.ceil((OG_H + gap) / (tile + gap)))
    canvas_h = rows * tile + gap * (rows - 1)

    canvas = Image.new("RGB", (OG_W, canvas_h), (17, 17, 17))
    for i, im in enumerate(images[: rows * cols]):
        r, c = divmod(i, cols)
        canvas.paste(square_crop(im, tile), (c * (tile + gap), r * (tile + gap)))

    top = max(0, (canvas_h - OG_H) // 2)
    card = canvas.crop((0, top, OG_W, top + OG_H))

    if title:
        # scrim so text stays legible over whatever the images happen to be
        scrim = Image.new("RGBA", (OG_W, OG_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(scrim)
        for y in range(OG_H // 2, OG_H):
            a = int(200 * (y - OG_H // 2) / (OG_H / 2))
            d.line([(0, y), (OG_W, y)], fill=(0, 0, 0, a))
        card = Image.alpha_composite(card.convert("RGBA"), scrim).convert("RGB")

        d = ImageDraw.Draw(card)
        f_title = load_font(76)
        d.text((60, OG_H - 150), title, font=f_title, fill=(255, 255, 255))
        if subtitle:
            f_sub = load_font(30)
            d.text((64, OG_H - 60), subtitle, font=f_sub, fill=(190, 190, 190))

    return card


def save(card, path, quality=85):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if path.lower().endswith(".png"):
        card.save(path, "PNG", optimize=True)
    else:
        card.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
    kb = os.path.getsize(path) / 1024
    flag = "  <-- over 1MB, some unfurlers will skip it" if kb > 1024 else ""
    print(f"{path}  {card.size[0]}x{card.size[1]}  {kb:.0f} KB{flag}")


# ---------------------------------------------------------------- main

def pick(keys, n, seed):
    rng = random.Random(seed)                 # deterministic per set
    return rng.sample(keys, min(n, len(keys)))


def gather(source, bucket, prefix, name, n, seed):
    """Return up to n opened images for one set."""
    if source:
        keys = list_local(source)
        if not keys:
            raise SystemExit(f"{name}: no images in {source}")
        return [open_local(k) for k in pick(keys, n, seed)]
    keys = list_s3(bucket, prefix)
    if not keys:
        raise SystemExit(f"{name}: no images under s3://{bucket}/{prefix}")
    return [open_s3(bucket, k) for k in pick(keys, n, seed)]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", default=os.environ.get("S3_BUCKET", ""))
    p.add_argument("--prefix", help="where the raw data actually is")
    p.add_argument("--map", help="YAML/JSON mapping of set name -> prefix")
    p.add_argument("--set", help="single set name")
    p.add_argument("--source", help="local directory instead of S3 (for testing)")
    p.add_argument("--out", default="assets/og")
    p.add_argument("--cols", type=int, default=6, help="tiles across (default 6)")
    p.add_argument("--gap", type=int, default=0, help="px between tiles (default 0)")
    p.add_argument("--ext", default="jpg", choices=["jpg", "png"])
    p.add_argument("--title", action="store_true", help="overlay the set name")
    p.add_argument("--subtitle", default="theunending.ai")
    p.add_argument("--site", action="store_true",
                   help="also build site.<ext> sampled across every run in --map")
    args = p.parse_args()

    pairs = {}
    if args.map:
        text = open(args.map).read()
        try:
            pairs = json.loads(text)
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                pairs[k.strip()] = v.strip().strip("\"'")
    elif args.set:
        pairs = {args.set: args.prefix}
    else:
        p.error("need --map or --set")

    if not args.source and not args.bucket:
        p.error("need --bucket (or S3_BUCKET) unless --source is given")

    per_card = args.cols * max(1, math.ceil(OG_H / (OG_W / args.cols)))

    for name, prefix in pairs.items():
        imgs = gather(args.source, args.bucket, prefix, name, per_card, name)
        card = build_card(imgs, args.cols, args.title and name.replace("-", " ").title() or None,
                          args.subtitle if args.title else None, args.gap)
        save(card, os.path.join(args.out, f"{name}.{args.ext}"))

    if args.site:
        # a few from each run so the site card isn't just one theme
        imgs, per_run = [], max(1, per_card // max(1, len(pairs)) + 1)
        for name, prefix in pairs.items():
            imgs += gather(args.source, args.bucket, prefix, name, per_run, f"site-{name}")
        random.Random("site").shuffle(imgs)
        card = build_card(imgs, args.cols, "The Unending" if args.title else None,
                          args.subtitle if args.title else None, args.gap)
        save(card, os.path.join(args.out, f"site.{args.ext}"))


if __name__ == "__main__":
    main()
