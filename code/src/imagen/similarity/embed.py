"""Command line interface for local PE Core image embeddings."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from .encoder import DEFAULT_MODEL, MODELS, PEEncoder, iter_images


def _sidecar(out: Path) -> Path:
    return out.with_suffix(out.suffix + ".json")


def _progress(done: int, total: int) -> None:
    print(f"\r  embedded {done}/{total}", end="", file=sys.stderr, flush=True)


def handle(args: argparse.Namespace) -> int:
    paths = iter_images(args.paths, recursive=not args.no_recursive)
    if not paths:
        print("No images found.", file=sys.stderr)
        return 1

    path_count = len(paths)
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    model = args.model or DEFAULT_MODEL
    print(f"Loading {model} ...", file=sys.stderr)
    started = time.perf_counter()
    encoder = PEEncoder.load(model, device=args.device, dtype=args.dtype)
    print(
        f"  {encoder.model_id} on {encoder.device.type} "
        f"({encoder.image_size}px, {args.dtype}) in {time.perf_counter() - started:.1f}s",
        file=sys.stderr,
    )

    if out.exists():
        E = np.load(str(out))
        if (E.shape[0] == path_count) and (not args.force):
            print(f"Embedding file {out} already exists and appears complete")
            return 0

    started = time.perf_counter()
    vectors = encoder.embed(
        paths,
        batch_size=args.batch_size,
        normalize=not args.no_normalize,
        on_batch=_progress,
    )
    elapsed = time.perf_counter() - started
    print(
        f"\r  embedded {len(paths)}/{len(paths)} in {elapsed:.1f}s "
        f"({elapsed / max(len(paths), 1) * 1000:.0f} ms/image)",
        file=sys.stderr,
    )

    if args.format == "jsonl":
        with out.open("w") as handle:
            for path, vector in zip(paths, vectors):
                handle.write(
                    json.dumps({"path": str(path), "embedding": vector.tolist()}) + "\n"
                )
        print(f"Wrote {out} ({len(paths)} x {vectors.shape[1]})")
    else:
        np.save(out, vectors)
        # np.save *appends* .npy when the name lacks it ("v1.dat" -> "v1.dat.npy"),
        # so mirror that rather than replacing the existing suffix.
        saved = out if out.suffix == ".npy" else out.with_name(out.name + ".npy")
        _sidecar(saved).write_text(
            json.dumps(
                {
                    "model": encoder.model_id,
                    "dim": int(vectors.shape[1]),
                    "normalized": not args.no_normalize,
                    "paths": [str(p) for p in paths],
                },
                indent=2,
            )
        )
        print(f"Wrote {saved} ({len(paths)} x {vectors.shape[1]}) and {_sidecar(saved)}")

    return 0


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("paths", nargs="+", help="image files and/or directories")
    parser.add_argument("-o", "--out", default="embeddings.npy", help="output path")
    parser.add_argument(
        "--format", default="npy", choices=["npy", "jsonl"], help="output format [npy]"
    )
    parser.add_argument("--batch-size", type=int, default=8, help="images per batch [8]")
    parser.add_argument(
        "--no-normalize", action="store_true", help="skip L2 normalization"
    )
    parser.add_argument(
        "--no-recursive", action="store_true", help="do not descend into subfolders"
    )
    parser.add_argument(
        "--force", action="store_true", help="force recreation if complete detected"
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"short name ({', '.join(MODELS)}) or a hub repo id [{DEFAULT_MODEL}]",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "mps", "cpu", "cuda"],
        help="compute device [auto]",
    )
    parser.add_argument(
        "--dtype",
        default="float32",
        choices=["float32", "float16", "bfloat16"],
        help="model precision [float32]",
    )
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
