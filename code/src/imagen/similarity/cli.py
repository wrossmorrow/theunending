import argparse

from .embed import command as embed_command
from .review import command as review_command


def commands(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    embed_command(subparsers.add_parser("embed", help="Embed images"))
    review_command(subparsers.add_parser("review", help="Review image embeddings"))
    return parser


def cli() -> argparse.Namespace:
    parser = commands(argparse.ArgumentParser())
    return parser.parse_args()
