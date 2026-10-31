import argparse

from .evaluate import command as eval_command
from .batch import command as batch_command
from .modal import command as modal_command


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")
    eval_command(subparsers.add_parser("eval", help="Evaluate prompts"))
    batch_command(subparsers.add_parser("batch", help="Run a batch"))
    modal_command(subparsers.add_parser("modal", help="Test modal"))
    return parser.parse_args()
