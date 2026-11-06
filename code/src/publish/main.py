from .cli import cli


def main():
    args = cli()
    args.func(args)
