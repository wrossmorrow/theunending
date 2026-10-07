"""Command line interface for local PE Core image embeddings."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from .encoder import DEFAULT_MODEL, MODELS, PEEncoder, iter_images, pick_device


def _sidecar(out: Path) -> Path:
    return out.with_suffix(out.suffix + ".json")


def _progress(done: int, total: int) -> None:
    print(f"\r  embedded {done}/{total}", end="", file=sys.stderr, flush=True)


def clean_path(p: str) -> str:
    return p.split("/")[-1].split(".")[0]


def cmd_embed(args: argparse.Namespace) -> int:
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


def cmd_similar(args: argparse.Namespace) -> int:
    index = Path(args.index).expanduser()
    vectors = np.load(index)
    meta = json.loads(_sidecar(index).read_text())
    paths = meta["paths"]

    # An index is only comparable against the model that built it, so default to
    # the model recorded in the sidecar rather than to whatever DEFAULT_MODEL is.
    model = args.model or meta.get("model") or DEFAULT_MODEL
    encoder = PEEncoder.load(model, device=args.device, dtype=args.dtype)
    query = encoder.embed([args.image], batch_size=1, normalize=True)[0]

    if query.shape[0] != vectors.shape[1]:
        print(
            f"Dimension mismatch: index is {vectors.shape[1]}-d (built with "
            f"{meta.get('model', 'unknown')}) but {encoder.model_id} produces "
            f"{query.shape[0]}-d. Re-embed the index with this model, or drop "
            "--model to use the one recorded in the sidecar.",
            file=sys.stderr,
        )
        return 1

    scores = vectors @ query  # both L2-normalized -> cosine similarity
    order = np.argsort(-scores)[: args.k]
    for rank, idx in enumerate(order, start=1):
        print(f"{rank:2d}. {scores[idx]:.4f}  {paths[idx]}")
    return 0


def cmd_review(args: argparse.Namespace):

    E = np.load(args.input)
    with open(f"{args.input}.json", "r") as f:
        meta = json.load(f)
        paths = meta["paths"]

    E = E / np.linalg.norm(E, axis=1, keepdims=True)   # L2-normalize → cosine = dot
    S = E @ E.T                                        # 5000×5000, ~100MB float32
    np.fill_diagonal(S, -1)                            # never recommend the image itself
    idx = np.argpartition(-S, 4, axis=1)[:, :4]        # then sort those 4 by score

    for i, p in enumerate(paths):
        indices = idx[i]
        path = clean_path(p)
        with open(f"{args.output}/{path}.json", "w") as f:
            f.write(json.dumps({
                "similar": [clean_path(paths[int(j)]) for j in indices]
            }))


def cmd_info(args: argparse.Namespace) -> int:
    import torch

    device = pick_device(args.device)
    print(f"torch          {torch.__version__}")
    print(f"mps available  {torch.backends.mps.is_available()}")
    print(f"device         {device.type}")
    print("models:")
    for short, repo in MODELS.items():
        marker = " (default)" if short == DEFAULT_MODEL else ""
        print(f"  {short:<5} {repo}{marker}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="embed",
        description="Local image embeddings from Meta's Perception Encoder (PE Core).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_model_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--model",
            default=None,
            help=f"short name ({', '.join(MODELS)}) or a hub repo id [{DEFAULT_MODEL}]",
        )
        p.add_argument(
            "--device",
            default="auto",
            choices=["auto", "mps", "cpu", "cuda"],
            help="compute device [auto]",
        )
        p.add_argument(
            "--dtype",
            default="float32",
            choices=["float32", "float16", "bfloat16"],
            help="model precision [float32]",
        )

    embed = sub.add_parser("embed", help="embed images or folders of images")
    embed.add_argument("paths", nargs="+", help="image files and/or directories")
    embed.add_argument("-o", "--out", default="embeddings.npy", help="output path")
    embed.add_argument(
        "--format", default="npy", choices=["npy", "jsonl"], help="output format [npy]"
    )
    embed.add_argument("--batch-size", type=int, default=8, help="images per batch [8]")
    embed.add_argument(
        "--no-normalize", action="store_true", help="skip L2 normalization"
    )
    embed.add_argument(
        "--no-recursive", action="store_true", help="do not descend into subfolders"
    )
    embed.add_argument(
        "--force", action="store_true", help="force recreation if complete detected"
    )
    add_model_flags(embed)
    embed.set_defaults(func=cmd_embed)

    similar = sub.add_parser("similar", help="rank an index against a query image")
    similar.add_argument("image", help="query image")
    similar.add_argument(
        "--index", default="embeddings.npy", help="an .npy written by `embed`"
    )
    similar.add_argument("-k", type=int, default=5, help="results to show [5]")
    add_model_flags(similar)
    similar.set_defaults(func=cmd_similar)

    review = sub.add_parser("review", help="review embeddings, compile JSONs")
    review.add_argument("--input", default="embeddings.npy", help="input path")
    review.add_argument("--output", default="results", help="output path")
    review.set_defaults(func=cmd_review)

    info = sub.add_parser("info", help="show device and model information")
    info.add_argument("--device", default="auto", choices=["auto", "mps", "cpu", "cuda"])
    info.set_defaults(func=cmd_info)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
