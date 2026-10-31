import argparse
import json

import numpy as np


def _clean_path(p: str) -> str:
    return p.split("/")[-1].split(".")[0]


def handle(input: str, output: str) -> None:

    E = np.load(input)
    with open(f"{input}.json", "r") as f:
        meta = json.load(f)
        paths = meta["paths"]

    E = E / np.linalg.norm(E, axis=1, keepdims=True)   # L2-normalize → cosine = dot
    S = E @ E.T                                        # 5000×5000, ~100MB float32
    np.fill_diagonal(S, -1)                            # never recommend the image itself
    idx = np.argpartition(-S, 4, axis=1)[:, :4]        # then sort those 4 by score

    print(idx.shape, idx)

    for i, p in enumerate(paths):
        indices = idx[i]
        path = _clean_path(p)
        with open(f"{output}/{path}.json", "w") as f:
            f.write(json.dumps({
                "similar": [_clean_path(paths[int(j)]) for j in indices]
            }))


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--input", default="embeddings.npy", help="input path")
    parser.add_argument("--output", default="results", help="output path")
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
