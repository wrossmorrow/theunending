import argparse

from ..og_tiles import command as og_tiles_command
from ..similarity import command as similarity_command
from ..full_posters import command as full_posters_command
from ..web_posters import command as web_posters_command


def run_similar(
    input: str,
    output: str,
) -> None:
    """
        uv run embed review \
            --input embeddings.npy \
            --output similar
    """
    parser = similarity_command(argparse.ArgumentParser())
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
    parser = og_tiles_command(argparse.ArgumentParser())
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
        poster_filename = f"{output}/{size}.png"
        run_poster(
            size,
            orientation,
            title,
            source,
            poster_filename,
            dpi=dpi,
            tile=tile,
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
    parser = full_posters_command(argparse.ArgumentParser())
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
    parser = web_posters_command(argparse.ArgumentParser())
    args = parser.parse_args(
        [
            "--source",
            source,
        ]
    )
    args.func(args)
