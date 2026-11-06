import argparse

from .. import og_tiles, web_posters
from ..similarity import review


def run_similar(
    input: str,
    output: str,
) -> None:
    """
        uv run embed review \
            --input embeddings.npy \
            --output similar
    """
    parser = review.command(argparse.ArgumentParser())
    args = parser.parse_args(
        [
            "--input",
            input,
            "--output",
            output,
        ]
    )
    args.func(args)


def run_og_tiles(
    set: str,
    prefix: str,
    source: str,
    output: str,
) -> None:
    """
        uv run imagen og-tiles \
            --set "${SET_NAME}" \
            --prefix "${RAW_PREFIX}" \
            --source ./images \
            --output og
    """
    parser = og_tiles.command(argparse.ArgumentParser())
    args = parser.parse_args(
        [
            "--set",
            set,
            "--prefix",
            prefix,
            "--source",
            source,
            "--output",
            output,
        ]
    )
    args.func(args)


def run_posters(
    sizes: dict[str, str],
    title: str,
    source: str,
    output: str,
    dpi: int = 150,
    tile: float = 1.5,
) -> None:
    for size, orientation in sizes.items():
        run_poster(
            size,
            orientation,
            dpi,
            tile,
            title,
            source,
            output,
        )


def run_poster(
    poster: str,
    orientation: str,
    title: str,
    source: str,
    output: str,
    dpi: int = 150,
    tile: float = 1.5,
) -> None:
    """
        uv run imagen full-posters \
            --poster "${SIZE}" \
            --orientation "${ORIENTATION}" \
            --dpi 150 \
            --tile 1.5 \
            --title "${POST_TITLE}" \
            --source "${SITE_IMG_ASSETS}" \
            --output ${OUTPUT_NAME}
    """
    parser = og_tiles.command(argparse.ArgumentParser())
    args = parser.parse_args(
        [
            "--poster",
            poster,
            "--orientation",
            orientation,
            "--dpi",
            str(dpi),
            "--tile",
            str(tile),
            "--title",
            title,
            "--source",
            source,
            "--output",
            output,
        ]
    )
    args.func(args)


def run_web_posters(
    source: str,
) -> None:
    """
    uv run imagen web-posters --source posters
    """
    parser = web_posters.command(argparse.ArgumentParser())
    args = parser.parse_args(
        [
            "--source",
            source,
        ]
    )
    args.func(args)
