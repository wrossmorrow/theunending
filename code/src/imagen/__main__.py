from .cli import cli


def main():
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
