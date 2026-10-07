#!/usr/bin/env python3
"""Make web-sized versions of full-resolution posters.

  posters/<WxH>/<name>.png  ->  posters/thumbs/<name>/<WxH>.webp     (<= 0.5 MB, grid tile)
                                posters/previews/<name>/<WxH>.webp   (<= 1 MB, click-through)
                                posters/web.json                     (index for the page)
                                posters/unending-posters.json        (restructured index for the page)

Each output starts at its target long edge and the encoder quality is binary-searched
to the largest value under the byte budget; if even the floor quality is too big the
image is shrunk 15% and the search repeats. Sources are never upscaled. Outputs newer
than their source are skipped unless --force.

  python web_versions.py posters [--thumb-px 900] [--preview-px 2400] [--format webp|jpg]
"""
import argparse
import io
import json
import os
import re
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # big posters (e.g. 36x48 @ 300 dpi) trip the bomb check
SIZE_DIR = re.compile(r"^\d+(\.\d+)?x\d+(\.\d+)?$")


def encode(im, fmt, q):
    buf = io.BytesIO()
    if fmt == "WEBP":
        im.save(buf, "WEBP", quality=q, method=6)
    else:
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True, subsampling="4:2:0")
    return buf.getvalue()


def fit_budget(src, long_px, max_bytes, fmt, q_lo=55, q_hi=90):
    """Return (bytes, (w, h), quality): largest quality <= budget, shrinking if needed."""
    long_px = min(long_px, max(src.size))
    while True:
        im = src.copy()
        im.thumbnail((long_px, long_px), Image.LANCZOS, reducing_gap=3.0)
        best, lo, hi = None, q_lo, q_hi
        while lo <= hi:
            q = (lo + hi) // 2
            data = encode(im, fmt, q)
            if len(data) <= max_bytes:
                best, lo = (data, im.size, q), q + 1
            else:
                hi = q - 1
        if best:
            return best
        long_px = int(long_px * 0.85)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("root", help="the posters/ directory")
    p.add_argument("--thumb-px", type=int, default=900, help="thumbnail long edge (default 900)")
    p.add_argument("--thumb-kb", type=int, default=500)
    p.add_argument("--preview-px", type=int, default=2400, help="preview long edge (default 2400)")
    p.add_argument("--preview-kb", type=int, default=1000)
    p.add_argument("--format", choices=["webp", "jpg"], default="webp")
    p.add_argument("--force", action="store_true", help="rebuild even if outputs are up to date")
    a = p.parse_args()

    fmt = "WEBP" if a.format == "webp" else "JPEG"
    index = []
    for size in sorted(os.listdir(a.root)):
        sdir = os.path.join(a.root, size)
        if not (SIZE_DIR.match(size) and os.path.isdir(sdir)):
            continue  # skips thumbs/, previews/, stray files
        for fn in sorted(os.listdir(sdir)):
            if not fn.lower().endswith((".png", ".tif", ".tiff", ".jpg", ".jpeg")):
                continue
            src_path = os.path.join(sdir, fn)
            name = os.path.splitext(fn)[0]
            entry = {"name": name, "size": size}
            src = None
            for kind, px, kb in (("previews", a.preview_px, a.preview_kb),
                                 ("thumbs", a.thumb_px, a.thumb_kb)):
                out = os.path.join(a.root, kind, name, f"{size}.{a.format}")
                rel = os.path.relpath(out, a.root)
                if (not a.force and os.path.exists(out)
                        and os.path.getmtime(out) >= os.path.getmtime(src_path)):
                    with Image.open(out) as im:
                        entry[kind[:-1]] = {"src": rel, "w": im.width, "h": im.height}
                    continue
                if src is None:
                    src = Image.open(src_path).convert("RGB")
                data, (w, h), q = fit_budget(src, px, kb * 1000, fmt)
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(data)
                entry[kind[:-1]] = {"src": rel, "w": w, "h": h}
                print(f"{rel}: {w}x{h} q{q} {len(data) / 1000:.0f} KB", file=sys.stderr)
            index.append(entry)

    with open(os.path.join(a.root, "web.json"), "w") as f:
        json.dump(index, f, indent=1)

    restructured: dict = {}
    for d in index:
        name = d["name"]
        size = d["size"]
        if name not in restructured:
            restructured[name] = {}
        restructured[name][size] = d

    with open(os.path.join(a.root, "unending-posters.json"), "w") as f:
        json.dump(restructured, f, indent=1)

    print(f"{len(index)} posters indexed in {os.path.join(a.root, 'web.json')}", file=sys.stderr)


if __name__ == "__main__":
    main()
