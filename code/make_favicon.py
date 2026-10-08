#!/usr/bin/env python3
"""
Generate a full favicon set from a short string.

    ./make_favicon.py --text Un --out assets/icons --palette dark

The SVG gets its glyphs converted to outlines with fontTools rather than
referenced by font-family, so it renders identically on a machine that has
never heard of the typeface. The PNGs are drawn by PIL from the same font,
supersampled 16x and downsampled, and both paths centre on the INK bounding
box rather than the font's line box -- otherwise ascender and descender
metrics push a cap-height string like "Un" visibly high in the tile.
"""

import argparse
import json
import os

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

VIEW = 64          # SVG user-space box
SS = 16            # supersample factor for the PNGs

PALETTES = {
    "dark":  {"bg": "#111111", "fg": "#ffffff"},
    "light": {"bg": "#ffffff", "fg": "#111111"},
}


def compose(font_path, text):
    """(svg path data, ink bounds) for the string, in font units."""
    font = TTFont(font_path, fontNumber=0)
    glyphset = font.getGlyphSet()
    cmap = font.getBestCmap()

    names = []
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            raise SystemExit(f"font has no glyph for {ch!r}")
        names.append(name)

    def run(pen):
        x = 0
        for name in names:
            glyphset[name].draw(TransformPen(pen, Transform().translate(x, 0)))
            x += glyphset[name].width

    bounds = BoundsPen(glyphset)
    run(bounds)
    if bounds.bounds is None:
        raise SystemExit("no ink in that string")

    svg = SVGPathPen(glyphset)
    run(svg)
    return svg.getCommands(), bounds.bounds


def placement(bounds, pad_ratio):
    """Scale and translation centring the ink in a VIEW box, y axis flipped."""
    xmin, ymin, xmax, ymax = bounds
    w, h = xmax - xmin, ymax - ymin
    target = VIEW * (1 - 2 * pad_ratio)
    scale = target / max(w, h)
    tx = (VIEW - w * scale) / 2 - xmin * scale
    ty = (VIEW + h * scale) / 2 + ymin * scale
    return scale, tx, ty


def write_svg(path, d, bounds, pal, pad_ratio):
    scale, tx, ty = placement(bounds, pad_ratio)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW} {VIEW}">'
        f'<rect width="{VIEW}" height="{VIEW}" fill="{pal["bg"]}"/>'
        f'<g transform="translate({tx:.4f} {ty:.4f}) scale({scale:.6f} {-scale:.6f})">'
        f'<path fill="{pal["fg"]}" d="{d}"/>'
        f'</g></svg>\n'
    )
    with open(path, "w") as fh:
        fh.write(svg)


def fit(draw, text, font_path, box, pad_ratio):
    """Largest point size whose ink fits the box with the given padding."""
    target = box * (1 - 2 * pad_ratio)
    lo, hi, best = 4, box * 2, None
    while lo <= hi:
        mid = (lo + hi) // 2
        f = ImageFont.truetype(font_path, mid)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if (r - l) <= target and (b - t) <= target:
            best, lo = (mid, (l, t, r, b)), mid + 1
        else:
            hi = mid - 1
    if best is None:
        raise SystemExit("could not fit the text")
    return best


def raster(font_path, text, size, pal, pad_ratio):
    big = size * SS
    im = Image.new("RGB", (big, big), pal["bg"])
    d = ImageDraw.Draw(im)
    px, (l, t, r, b) = fit(d, text, font_path, big, pad_ratio)
    f = ImageFont.truetype(font_path, px)
    d.text(((big - (r - l)) / 2 - l, (big - (b - t)) / 2 - t),
           text, font=f, fill=pal["fg"])
    return im.resize((size, size), Image.LANCZOS)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--text", default="Un")
    p.add_argument("--font",
                   default="/usr/share/texmf/fonts/opentype/public/tex-gyre/texgyrebonum-bold.otf")
    p.add_argument("--out", default="assets/icons")
    p.add_argument("--palette", default="dark", choices=list(PALETTES))
    p.add_argument("--pad", type=float, default=0.14)
    p.add_argument("--name", default="The Unending")
    args = p.parse_args()

    pal = PALETTES[args.palette]
    os.makedirs(args.out, exist_ok=True)

    d, bounds = compose(args.font, args.text)
    write_svg(os.path.join(args.out, "favicon.svg"), d, bounds, pal, args.pad)

    for s in (16, 32, 48, 96, 192, 512):
        raster(args.font, args.text, s, pal, args.pad).save(
            os.path.join(args.out, f"icon-{s}.png"))

    # iOS rounds the corners itself and never shows transparency, so the touch
    # icon is opaque and sits a little further from the edge than a tab icon
    raster(args.font, args.text, 180, pal, args.pad + 0.06).save(
        os.path.join(args.out, "apple-touch-icon.png"))

    raster(args.font, args.text, 48, pal, args.pad).save(
        os.path.join(args.out, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])

    manifest = {
        "name": args.name,
        "short_name": args.text,
        "icons": [
            {"src": "/assets/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": pal["bg"],
        "background_color": pal["bg"],
        "display": "browser",
    }
    with open(os.path.join(args.out, "site.webmanifest"), "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    for f in sorted(os.listdir(args.out)):
        print(f"  {f:24s} {os.path.getsize(os.path.join(args.out, f)):6d} bytes")


if __name__ == "__main__":
    main()
