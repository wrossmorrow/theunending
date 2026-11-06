import argparse

from .full_posters import command as fp_command
from .og_tiles import command as ogt_command
from .publish import command as publish_command
from .similarity import command as sim_command
from .web_posters import command as wp_command


def commands(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Available commands"
    )
    sim_command(subparsers.add_parser("similarity", help="Similarity evals"))
    ogt_command(subparsers.add_parser("og-tiles", help="OG tiles"))
    fp_command(subparsers.add_parser("full-posters", help="Full posters"))
    wp_command(subparsers.add_parser("web-posters", help="Web posters"))
    publish_command(subparsers.add_parser("publish", help="Publish results"))
    return parser


def cli() -> argparse.Namespace:
    parser = commands(argparse.ArgumentParser())
    return parser.parse_args()
