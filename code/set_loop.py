#!/usr/bin/env python3
"""
Build a looping grid animation from a set's images.

    # local directory, for testing
    ./set_loop.py --set demo --source ./some/dir --out assets/loops

    # one set from S3
    ./set_loop.py --set computation --run 17 --out assets/loops

    # every set in a mapping file (YAML "set: run" per line, or JSON)
    ./set_loop.py --map og_runs.yml --out assets/loops

The animation has three movements:

  fill    the grid starts empty and tiles land one at a time
  cycle   tiles are replaced, one per frame, in a shuffled order
  drain   tiles are removed one at a time until the grid is empty again

The drain exists because of a GIF constraint worth understanding: a GIF loop
always restarts at frame 1, and there is no way to play an intro once and then
loop a later subset. So either the fill replays as a visible jump cut, or the
animation returns to the state it started in and the seam disappears. Draining
is the second. Pass --no-drain for the jump cut.

Both outputs are written from the same frames. GIF is capped at 256 colours
for the entire animation, which photographic tiles do not enjoy; WebP has no
such limit and lands several times smaller. Use the WebP wherever you can.
"""

import argparse
import io
import json
import math
import os
import random
import sys
import shutil
import subprocess
import tempfile

from PIL import Image

BG_NAMES = {"white": (255, 255, 255), "black": (0, 0, 0), "paper": (250, 249, 246)}


# ---------------------------------------------------------------- sources

def list_local(path):
    return sorted(
        os.path.join(path, n) for n in os.listdir(path)
        if n.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    )


def list_s3(bucket, prefix):
    import boto3
    s3 = boto3.client("s3")
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].lower().endswith((".png", ".jpg", ".jpeg")):
                keys.append(obj["Key"])
    return sorted(keys)


def open_s3(bucket, key):
    import boto3
    s3 = boto3.client("s3")
    return Image.open(io.BytesIO(s3.get_object(Bucket=bucket, Key=key)["Body"].read()))


def square_crop(im, size):
    w, h = im.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    return (im.crop((left, top, left + side, top + side))
              .convert("RGB")
              .resize((size, size), Image.LANCZOS))


def gather(source, bucket, prefix, name, count, seed, tile):
    """Return `count` tiles, cropped and sized, deterministically chosen."""
    if source:
        keys = list_local(source)
        opener = Image.open
        where = source
    else:
        keys = list_s3(bucket, prefix)
        opener = lambda k: open_s3(bucket, k)      # noqa: E731
        where = f"s3://{bucket}/{prefix}"
    if not keys:
        raise SystemExit(f"{name}: no images in {where}")
    if len(keys) < count:
        print(f"  {name}: only {len(keys)} images, wanted {count} -- reusing some",
              file=sys.stderr)
        keys = (keys * math.ceil(count / len(keys)))[:count]
    picked = random.Random(seed).sample(keys, count)
    return [square_crop(opener(k), tile) for k in picked]


# ---------------------------------------------------------------- frames

def q10(ms):
    """Round a duration to something GIF can actually store.

    GIF keeps frame delays in centiseconds, so 45ms silently becomes 40ms and
    the GIF and the WebP drift out of sync. Quantising here keeps both formats
    identical by construction. The floor of 20ms is a second GIF quirk: most
    browsers treat a delay below 20ms as 100ms, so a "faster" value runs five
    times slower than asked.
    """
    return max(20, int(round(ms / 10.0)) * 10)


def build_frames(tiles, cols, rows, tile, gap, bg, swaps, drain, rng):
    """Return (frames, durations_ms). One cell changes per frame."""
    cells = cols * rows
    W = cols * tile + gap * (cols - 1)
    H = rows * tile + gap * (rows - 1)

    def blank():
        return Image.new("RGB", (W, H), bg)

    def xy(i):
        r, c = divmod(i, cols)
        return c * (tile + gap), r * (tile + gap)

    canvas = blank()
    frames, durs = [canvas.copy()], []
    durs.append(q10(220))                  # a beat on the empty grid

    # fill: left to right, row by row, the way the site's stream fills
    for i in range(cells):
        canvas.paste(tiles[i], xy(i))
        frames.append(canvas.copy())
        durs.append(q10(70))
    durs[-1] = q10(700)                         # hold once the grid is complete

    # cycle: replace cells in a shuffled order so it does not read as a wipe
    order = list(range(cells))
    rng.shuffle(order)
    for n in range(swaps):
        cell = order[n % cells]
        canvas.paste(tiles[cells + n], xy(cell))
        frames.append(canvas.copy())
        durs.append(q10(160))
    durs[-1] = q10(520)

    if drain:
        # remove in a different shuffled order, so the exit is not the entrance
        out = list(range(cells))
        rng.shuffle(out)
        patch = Image.new("RGB", (tile, tile), bg)
        for i in out:
            canvas.paste(patch, xy(i))
            frames.append(canvas.copy())
            durs.append(q10(45))
        durs[-1] = q10(320)
        # the last frame is an empty grid, identical to the first, so the loop
        # has no seam -- drop it to avoid a double-length pause
        frames.pop()
        durs.pop()
        durs[-1] = q10(320)

    return frames, durs


def build_cycle_frames(tiles, cols, rows, tile, gap, bg, rings, rng, swap_ms=140):
    """Full grid throughout; the last frame leads back into the first.

    Each cell owns a ring of `rings` images and starts on ring[0]. Every round
    is a shuffled permutation of all cells, and a cell steps once per round, so
    after `rings` rounds every cell has returned to ring[0] -- the grid is back
    to its opening configuration by construction rather than by coincidence.
    The duplicate final frame is dropped, which turns the loop point into one
    more single-tile swap.

    Timing is deliberately uniform. A hold anywhere marks a position, and a
    marked position is a visible seam.
    """
    cells = cols * rows
    need = cells * rings
    if len(tiles) < need:
        raise SystemExit(f"need {need} images for {cols}x{rows} with rings={rings}")
    ring = [tiles[i * rings:(i + 1) * rings] for i in range(cells)]

    W = cols * tile + gap * (cols - 1)
    H = rows * tile + gap * (rows - 1)

    def xy(i):
        r, c = divmod(i, cols)
        return c * (tile + gap), r * (tile + gap)

    canvas = Image.new("RGB", (W, H), bg)
    for i in range(cells):
        canvas.paste(ring[i][0], xy(i))

    frames, durs = [canvas.copy()], [swap_ms]
    for step in range(1, rings + 1):
        order = list(range(cells))
        rng.shuffle(order)                 # a fresh order each round
        for cell in order:
            canvas.paste(ring[cell][step % rings], xy(cell))
            frames.append(canvas.copy())
            durs.append(swap_ms)

    frames.pop()                           # identical to frames[0]
    durs.pop()
    return frames, durs


def shared_palette(frames, bg):
    """One palette for every frame.

    Two reasons. A per-frame palette makes the whole image shimmer as the
    palette shifts under unchanged tiles. And a shared palette lets PIL write
    each frame as a delta against the previous one -- with a single tile
    changing per frame, that is the difference between a 15MB file and a small
    one.
    """
    # sample from the busiest frame, which has every tile on screen at once
    busiest = max(frames, key=lambda f: len(f.getcolors(maxcolors=1 << 24) or [1]))
    pal = busiest.quantize(colors=255, method=Image.MEDIANCUT)
    # force the background into the palette so the gaps stay exactly one colour
    pal_bytes = bytearray(pal.getpalette())
    pal_bytes[765:768] = bytes(bg)
    pal.putpalette(bytes(pal_bytes))
    return pal


def save_gif(path, frames, durs, bg):
    pal = shared_palette(frames, bg)
    conv = [f.quantize(palette=pal, dither=Image.FLOYDSTEINBERG) for f in frames]
    conv[0].save(
        path, save_all=True, append_images=conv[1:],
        duration=durs, loop=0, optimize=True, disposal=1,
    )


def save_webp(path, frames, durs, quality):
    frames[0].save(
        path, format="WEBP", save_all=True, append_images=frames[1:],
        duration=durs, loop=0, quality=quality, method=6, minimize_size=True,
    )


def save_mp4(path, frames, durs, fps=30, crf=18):
    """Encode frames to H.264 at a constant frame rate.

    The frames carry per-frame durations in milliseconds; video needs a fixed
    rate, so the concat demuxer resamples -- each frame is held for as many
    video frames as its duration covers. yuv420p is not optional: without it
    the file plays in ffplay and VLC and fails on phones and in browsers.
    """
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found; brew install ffmpeg")
    
    # ffmpeg picks its container from the extension, so a .webp path here
    # silently becomes a WebP encode with libx264 and fails deep in the muxer
    if not path.lower().endswith(".mp4"):
        raise SystemExit(f"save_mp4 needs an .mp4 path, got {path!r}")

    w, h = frames[0].size
    if w % 2 or h % 2:
        raise SystemExit(f"H.264 needs even dimensions, got {w}x{h}")

    tmp = tempfile.mkdtemp(prefix="loop-mp4-")
    try:
        listing = os.path.join(tmp, "frames.txt")
        with open(listing, "w") as fh:
            for i, (frame, ms) in enumerate(zip(frames, durs)):
                p = os.path.join(tmp, f"f{i:05d}.png")
                frame.save(p)
                fh.write(f"file '{p}'\nduration {ms / 1000:.4f}\n")
            # concat needs the final image repeated or it gets no duration
            fh.write(f"file '{os.path.join(tmp, f'f{len(frames)-1:05d}.png')}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", listing,
            "-r", str(fps),
            "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            path,
        ], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- main

def report(path):
    kb = os.path.getsize(path) / 1024
    flag = ""
    if path.endswith(".gif") and kb > 2048:
        flag = "   <-- over 2MB, Slack and most feeds will transcode it"
    print(f"  {path}  {kb:,.0f} KB{flag}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", default=os.environ.get("S3_BUCKET", ""))
    p.add_argument("--prefix", help="run prefix for --set")
    p.add_argument("--map", help="YAML/JSON mapping of set name -> run id")
    p.add_argument("--set", help="single set name")
    p.add_argument("--source", help="local directory instead of S3 (for testing)")
    p.add_argument("--mode", default="cycle", choices=["cycle", "fill"])
    p.add_argument("--rings", type=int, default=3,
                   help="images each cell cycles through (cycle mode)")
    p.add_argument("--out", default="assets/loops")
    p.add_argument("--cols", type=int, default=4)
    p.add_argument("--rows", type=int, default=5)
    p.add_argument("--width", type=int, default=720, help="output width in px")
    p.add_argument("--gap", type=int, default=2)
    p.add_argument("--bg", default="white", help="white, black, paper, or #rrggbb")
    p.add_argument("--swaps", type=int, default=None,
                   help="cycle frames (default: one per cell)")
    p.add_argument("--no-drain", dest="drain", action="store_false",
                   help="end on a full grid; the loop will visibly jump")
    p.add_argument("--quality", type=int, default=80, help="WebP quality")
    p.add_argument("--no-gif", dest="gif", default=True, action="store_false")
    p.add_argument("--no-webp", dest="webp", default=True, action="store_false")
    p.add_argument("--no-mp4", dest="mp4", default=True, action="store_false")
    args = p.parse_args()

    if args.bg.startswith("#"):
        h = args.bg.lstrip("#")
        bg = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    elif args.bg in BG_NAMES:
        bg = BG_NAMES[args.bg]
    else:
        p.error(f"unknown --bg {args.bg!r}")

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

    cells = args.cols * args.rows
    swaps = args.swaps if args.swaps is not None else cells
    tile = (args.width - args.gap * (args.cols - 1)) // args.cols
    if tile < 8:
        p.error("tiles would be under 8px; raise --width or lower --cols")

    os.makedirs(args.out, exist_ok=True)
    for name, prefix in pairs.items():
        rng = random.Random(name)              # deterministic per set

        need = cells * args.rings if args.mode == "cycle" else cells + swaps
        tiles = gather(args.source, args.bucket, prefix, name, need, name, tile)
        if args.mode == "cycle":
            frames, durs = build_cycle_frames(tiles, args.cols, args.rows, tile,
                                              args.gap, bg, args.rings, rng)
        else:
            frames, durs = build_frames(tiles, args.cols, args.rows, tile, args.gap,
                                        bg, swaps, args.drain, rng)

        total = sum(durs) / 1000
        print(f"{name}: {len(frames)} frames, {total:.1f}s, "
              f"{args.cols}x{args.rows} at {tile}px")
        if args.gif:
            path = os.path.join(args.out, f"{name}.gif")
            save_gif(path, frames, durs, bg)
            report(path)
        if args.webp:
            path = os.path.join(args.out, f"{name}.webp")
            save_webp(path, frames, durs, args.quality)
            report(path)
        if args.mp4:
            path = os.path.join(args.out, f"{name}.mp4")
            save_mp4(path, frames, durs)
            report(path)


if __name__ == "__main__":
    main()
