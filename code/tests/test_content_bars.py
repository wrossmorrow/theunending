from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from PIL import Image

from src.imagen.batch import check_image, content_bars

SOLID_BLACK = (0, 0, 0)
CONTENT_COLOR = (255, 255, 255)


def _solid_image(width: int, height: int, color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def _with_black_blocks(
    image: Image.Image,
    blocks: Sequence[tuple[int, int, int]],
) -> Image.Image:
    """Return a copy of ``image`` with solid-black squares painted at the given (row, col, size) origins."""
    result = image.copy()
    px = result.load()
    for row, col, size in blocks:
        for y in range(row, row + size):
            for x in range(col, col + size):
                px[x, y] = SOLID_BLACK
    return result


def _content_framed_image(
    width: int,
    height: int,
    top: int,
    bottom: int,
    left: int,
    right: int,
) -> Image.Image:
    """Build a white image whose content is inset by solid-black bars of the given sizes."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    arr[top : height - bottom, left : width - right] = CONTENT_COLOR
    return Image.fromarray(arr, "RGB")


def test_content_bars_full_frame_with_black_corner_blocks() -> None:
    """Full-frame content yields zero margins, even when black blocks sit in the corners."""
    image = _with_black_blocks(
        _solid_image(64, 64, CONTENT_COLOR), [(0, 0, 8), (56, 56, 8)]
    )

    assert content_bars(image) == (0, 0, 0, 0)


def test_check_image_accepts_full_frame_with_black_corner_blocks() -> None:
    image = _with_black_blocks(
        _solid_image(64, 64, CONTENT_COLOR), [(0, 0, 8), (56, 56, 8)]
    )

    assert check_image(image) is None


def test_content_bars_rejects_bars_above_min_frac() -> None:
    image = _content_framed_image(64, 64, top=16, bottom=16, left=16, right=16)

    assert content_bars(image) == (16, 16, 16, 16)
    assert check_image(image) == "letterboxed"


def test_check_image_accepts_bars_below_min_frac() -> None:
    image = _content_framed_image(512, 512, top=4, bottom=4, left=4, right=4)

    assert content_bars(image) == (4, 4, 4, 4)
    assert check_image(image) is None


def test_check_image_rejects_all_black_image() -> None:
    assert check_image(_solid_image(64, 64, SOLID_BLACK)) == "all-black"
