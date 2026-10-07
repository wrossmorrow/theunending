#!/usr/bin/env python3
"""Lay out 512x512 PNG tiles on a white poster.

Tiles are chosen at random, or by a random walk over each image's companion
<uuid>.json {"similar": [...]}; walk order is placed in a snake (boustrophedon)
pattern so consecutive walk steps stay neighbours on the poster.

Caption (on by default): "<title> · <cols> × <rows> · <ISO datetime>" in Helvetica
(or Liberation Sans/Arimo where Helvetica isn't installed), right-aligned with the
grid's right edge and centred vertically in the bottom margin.

Layout guarantees:
  * >= 1 inch white margin on every side (slack goes to the margins, centered)
  * identical gap (integer pixels) between all horizontal and vertical neighbours

CLI:
  python poster.py s3://bucket/prefix poster.png --poster 24x36 --orientation portrait \
      --tile 2 --dpi 150 --mode walk --seed 42
  (source can also be a local directory; output can be a local path or s3://bucket/key)

Lambda: handler = poster.lambda_handler, event = keyword args of build_poster(), e.g.
  {"source": "s3://b/imgs", "output": "s3://b/posters/p.png", "poster": "24x36",
   "orientation": "portrait", "tile": 2, "dpi": 150, "mode": "walk", "title": "Masks"}
Needs Pillow (layer or container image); boto3 is already in the runtime.
"""
import argparse
import io
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

MARGIN_IN = 1
EXPECTED_PX = 512
CAPTION_FILL = (121, 121, 121)

# Helvetica first (macOS), then metric-compatible clones common on Linux/Lambda layers
FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Helvetica.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/croscore/Arimo-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def log(msg):
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- storage ---
class Store:
    """Uniform read/list/write over s3://bucket/prefix or a local directory."""

    def __init__(self, uri):
        self.is_s3 = uri.startswith("s3://")
        if self.is_s3:
            import boto3
            self.s3 = boto3.client("s3")
            self.bucket, _, prefix = uri[5:].partition("/")
            self.prefix = prefix if not prefix or prefix.endswith("/") else prefix + "/"
        else:
            self.root = uri

    def list_ids(self):
        if not self.is_s3:
            return sorted(f[:-4] for f in os.listdir(self.root) if f.lower().endswith(".png"))
        ids = []
        pages = self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=self.prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                rest = obj["Key"][len(self.prefix):]
                if "/" not in rest and rest.lower().endswith(".png"):
                    ids.append(rest[:-4])
        return sorted(ids)

    def read(self, name):
        if self.is_s3:
            return self.s3.get_object(Bucket=self.bucket, Key=self.prefix + name)["Body"].read()
        with open(os.path.join(self.root, name), "rb") as f:
            return f.read()

    def similar(self, uid):
        try:
            return list(json.loads(self.read(uid + ".json")).get("similar", []))
        except Exception as e:  # missing/broken JSON -> dead end for the walk
            log(f"warn: no neighbours for {uid}: {e}")
            return []


def write_output(uri, data):
    if uri.startswith("s3://"):
        import boto3
        bucket, _, key = uri[5:].partition("/")
        boto3.client("s3").put_object(Bucket=bucket, Key=key, Body=data)
    else:
        with open(uri, "wb") as f:
            f.write(data)


# ---------------------------------------------------------------- caption ---
def load_font(px, path=None):
    for cand in ([path] if path else []) + FONT_CANDIDATES:
        if cand and os.path.exists(cand):
            return ImageFont.truetype(cand, px), cand
    log("warn: no Helvetica-like font found; using Pillow's built-in font")
    return ImageFont.load_default(px), "default"


def draw_caption(canvas, text, right, top, px, font_path=None):
    """Right-align text at x=right with the top of its visible ink at y=top."""
    font, used = load_font(px, font_path)
    draw = ImageDraw.Draw(canvas)
    _, t, _, b = draw.textbbox((right, top), text, font=font, anchor="ra")
    dy = top - t  # 'ra' anchors at the ascender line; shift so the glyph tops land on `top`
    if b + dy > canvas.height:
        log("warn: caption runs off the bottom of the poster")
    draw.text((right, top + dy), text, fill=CAPTION_FILL, font=font, anchor="ra")
    log(f"caption ({os.path.basename(used)}): {text}")


# ----------------------------------------------------------------- layout ---
def layout(W, H, s, min_gap, margin, stretch=True):
    """Grid that fits in (W,H) minus margins with uniform integer gap.

    cols/rows are the max that fit with min_gap; the gap is then widened to the
    largest single value that still fits both directions (so one axis ends up
    flush with the 1" margin), unless stretch=False.
    """
    uw, uh = W - 2 * margin, H - 2 * margin
    cols = (uw + min_gap) // (s + min_gap)
    rows = (uh + min_gap) // (s + min_gap)
    if cols < 1 or rows < 1:
        raise ValueError("tile size too large for poster minus 1in margins")
    gap = min_gap
    if stretch:
        cands = [(u - n * s) // (n - 1) for u, n in ((uw, cols), (uh, rows)) if n > 1]
        if cands:
            gap = min(cands)
    gw, gh = cols * s + (cols - 1) * gap, rows * s + (rows - 1) * gap
    return cols, rows, gap, (W - gw) // 2, (H - gh) // 2


def snake_positions(cols, rows):
    for r in range(rows):
        cs = range(cols) if r % 2 == 0 else range(cols - 1, -1, -1)
        for c in cs:
            yield r, c


# -------------------------------------------------------------- selection ---
def pick_random(ids, n, rng):
    if n <= len(ids):
        return rng.sample(ids, n)
    log(f"warn: need {n} tiles but only {len(ids)} images; repeating")
    return rng.choices(ids, k=n)


def pick_walk(store, ids, n, rng, lookback=20):
    if n > len(ids):
        raise ValueError(f"walk needs {n} distinct images, only {len(ids)} available")
    idset, seen, path, nbrs = set(ids), set(), [], {}
    cur, jumps = rng.choice(ids), 0
    while True:
        path.append(cur)
        seen.add(cur)
        if len(path) == n:
            break
        nbrs[cur] = [x for x in store.similar(cur) if x in idset]
        nxt = None
        # try current node, then backtrack through recent nodes for an unvisited neighbour
        for prev in reversed(path[-lookback:]):
            opts = [x for x in nbrs.get(prev, []) if x not in seen]
            if opts:
                nxt = rng.choice(opts)
                break
        if nxt is None:  # dead end: teleport
            jumps += 1
            nxt = rng.choice([x for x in ids if x not in seen])
        cur = nxt
    log(f"walk: {n} steps, {jumps} random restarts")
    return path


# ------------------------------------------------------------------ build ---
def load_tile(store, uid, s):
    im = Image.open(io.BytesIO(store.read(uid + ".png")))
    if im.size != (EXPECTED_PX, EXPECTED_PX):
        log(f"warn: {uid} is {im.size}, expected {EXPECTED_PX}x{EXPECTED_PX}")
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[-1])
        im = bg
    return im.convert("RGB").resize((s, s), Image.LANCZOS)


def build_poster(source, output, poster="24x36", orientation="portrait", tile=2.0,
                 dpi=150, mode="random", gap=0.125, stretch_gap=True, seed=None, workers=16,
                 omit_freq=0.0, title=None, caption=True, font=None, font_size=10):
    pw, ph = (float(x) for x in str(poster).lower().split("x"))
    short, long_ = sorted((pw, ph))
    w_in, h_in = (short, long_) if orientation == "portrait" else (long_, short)
    W, H = round(w_in * dpi), round(h_in * dpi)
    s, margin, min_gap = round(tile * dpi), round(MARGIN_IN * dpi), max(1, round(gap * dpi))
    if s > EXPECTED_PX:
        log(f"warn: tiles are {s}px, upsampling from {EXPECTED_PX}px "
            f"(native res at {dpi} dpi is {EXPECTED_PX / dpi:.2f} in)")

    cols, rows, g, x0, y0 = layout(W, H, s, min_gap, margin, stretch_gap)
    n = cols * rows
    log(f"poster {W}x{H}px, grid {cols}x{rows} = {n} tiles of {s}px, gap {g}px "
        f"({g / dpi:.3f} in), margins L/R {x0 / dpi:.2f} in, T/B {y0 / dpi:.2f} in")

    store = Store(source)
    ids = store.list_ids()
    if not ids:
        raise ValueError(f"no .png files found at {source}")
    rng = random.Random(seed)
    chosen = pick_walk(store, ids, n, rng) if mode == "walk" else pick_random(ids, n, rng)

    canvas = Image.new("RGB", (W, H), "white")
    with ThreadPoolExecutor(workers) as ex:
        tiles = ex.map(lambda u: load_tile(store, u, s), chosen)
        for (r, c), im in zip(snake_positions(cols, rows), tiles):
            if omit_freq > 0.0 and rng.random() <= omit_freq:
                continue
            canvas.paste(im, (x0 + c * (s + g), y0 + r * (s + g)))

    created = datetime.now().astimezone().isoformat(timespec="seconds")
    if caption:
        parts = ([title] if title else []) + [f"{cols} \u00d7 {rows} ({cols * rows} images)", "W. Ross Morrow", created]
        grid_right = x0 + cols * s + (cols - 1) * g   # exact edges, no centring rounding
        grid_bottom = y0 + rows * s + (rows - 1) * g
        draw_caption(canvas, "   \u00b7   ".join(parts), grid_right, grid_bottom + g,
                     round(font_size / 72 * dpi), font)

    fmt = {"jpg": "JPEG", "jpeg": "JPEG", "tif": "TIFF", "tiff": "TIFF"}.get(
        output.rsplit(".", 1)[-1].lower(), "PNG")
    buf = io.BytesIO()
    canvas.save(buf, fmt, dpi=(dpi, dpi), **({"quality": 95} if fmt == "JPEG" else {}))
    write_output(output, buf.getvalue())
    log(f"wrote {output} ({buf.tell() / 1e6:.1f} MB)")
    return {"output": output, "grid": [cols, rows], "gap_px": g, "created": created, "tiles": chosen}


def lambda_handler(event, context):
    if event["output"].endswith("/"):
        output = event["output"]
        requested = datetime.now().astimezone().isoformat(timespec="seconds")
        event["output"] = f"{output}{requested}.png"
    result = build_poster(**event)
    result.pop("tiles")  # keep the response small
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", help="s3://bucket/prefix or local directory of <uuid>.png (+ .json)")
    p.add_argument("output", help="output path or s3://bucket/key (.png/.jpg/.tif)")
    p.add_argument("--poster", default="24x36", help="poster size in inches, WxH (default 24x36)")
    p.add_argument("--orientation", choices=["portrait", "landscape"], default="portrait")
    p.add_argument("--tile", type=float, default=2.0, help="tile width in inches (default 2)")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--mode", choices=["random", "walk"], default="random")
    p.add_argument("--gap", type=float, default=0.125, help="minimum gap between tiles, inches")
    p.add_argument("--fixed-gap", action="store_true", help="use --gap exactly instead of widening it")
    p.add_argument("--seed", type=int)
    p.add_argument("--omit-freq", type=float, default=0.0)
    p.add_argument("--title", help="title printed in the bottom-right caption")
    p.add_argument("--no-caption", action="store_true", help="omit the bottom-right caption")
    p.add_argument("--font", help="path to a .ttf/.ttc (default: Helvetica, else a metric clone)")
    p.add_argument("--font-size", type=float, default=10, help="caption size in points (default 10)")
    p.add_argument("--manifest", help="optional: write chosen UUIDs (grid order, row-major) to this file")
    a = p.parse_args()
    res = build_poster(a.source, a.output, a.poster, a.orientation, a.tile, a.dpi, a.mode,
                       a.gap, not a.fixed_gap, a.seed, omit_freq=a.omit_freq,
                       title=a.title, caption=not a.no_caption, font=a.font, font_size=a.font_size)
    if a.manifest:
        cols = res["grid"][0]
        pos = list(snake_positions(cols, res["grid"][1]))
        grid = sorted(zip(pos, res["tiles"]))
        with open(a.manifest, "w") as f:
            json.dump({"grid": res["grid"], "rows": [[u for (r, _), u in grid if r == i]
                                                     for i in range(res["grid"][1])]}, f, indent=1)


if __name__ == "__main__":
    main()
