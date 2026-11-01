import argparse

from .batch import command as batch_command
from .evaluate import command as eval_command
from .full_posters import command as fp_command
from .modal import commands as modal_commands
from .og_tiles import command as ogt_command
from .similarity.cli import commands as sim_commands
from .web_posters import command as wp_command


def commands(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    eval_command(subparsers.add_parser("eval", help="Evaluate prompts"))
    batch_command(subparsers.add_parser("batch", help="Run a batch"))
    sim_commands(subparsers.add_parser("similarity", help="Similarity evals"))
    ogt_command(subparsers.add_parser("og-tiles", help="OG tiles"))
    fp_command(subparsers.add_parser("full-posters", help="Full posters"))
    wp_command(subparsers.add_parser("web-posters", help="Web posters"))
    modal_commands(subparsers.add_parser("modal", help="Test modal"))
    return parser


def cli() -> argparse.Namespace:
    parser = commands(argparse.ArgumentParser())
    return parser.parse_args()
