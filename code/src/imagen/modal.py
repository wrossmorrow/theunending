import argparse
import glob
import hashlib
import os

import boto3
import modal

from .evaluate import command as eval_command
from .batch import command as batch_command


DEFAULT_IGNORE_ARGS = {"func", "command"}
EVAL_TIMEOUT_SEC = 600  # 10 minutes
BATCH_TIMEOUT_SEC = 3600  # 1 hour
AWS_OIDC_ROLE_ARN = "arn:aws:iam::396610714890:role/modal-oidc-access"
AWS_OIDC_SESSION_DURATION_SECONDS = 7200  # 2 hours; check IAM limits


def _aws_creds(role_arn: str = AWS_OIDC_ROLE_ARN):
    sts_client = boto3.client("sts")
    response = sts_client.assume_role_with_web_identity(
        RoleArn=role_arn,
        RoleSessionName="ModalOIDCSession",
        WebIdentityToken=os.environ["MODAL_IDENTITY_TOKEN"],
        DurationSeconds=AWS_OIDC_SESSION_DURATION_SECONDS,
    )
    return response["Credentials"]


def _s3_client(role_arn: str = AWS_OIDC_ROLE_ARN):
    credentials = _aws_creds(role_arn=role_arn)
    return boto3.client(
        "s3",
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )


def _sanitize_args(
    args: argparse.Namespace, 
    ignore: set[str] = DEFAULT_IGNORE_ARGS,
) -> argparse.Namespace:
    return argparse.Namespace(**{k: v for k, v in vars(args).items() if k not in ignore})


img = modal.Image.from_name(name="theunending").env({
    "HF_HUB_OFFLINE": "1",
    "HF_HOME": "/cache",
})
app = modal.App("theunending", image=img)
vol = modal.Volume.from_name("hf-hub-cache")


@app.function()
def square(args: argparse.Namespace) -> int:
    print("This code is running on a remote worker!")
    return args.value ** 2


def handle_test(args: argparse.Namespace) -> None:
    with app.run():
        result = square.remote(_sanitize_args(args))
        print("the square is", result)


@app.function(
    gpu="A100",
    volumes={
        "/cache": vol,
    },
    timeout=EVAL_TIMEOUT_SEC,
)
def evaluate(args: argparse.Namespace) -> None:
    from .evaluate import handle as _handle_eval

    # NOTE!: get client on remote for OIDC
    _handle_eval(_sanitize_args(args), s3=_s3_client())


def handle_eval(args: argparse.Namespace) -> None:
    with app.run():
        evaluate.remote(args)


@app.function(
    gpu="A100",
    volumes={
        "/cache": vol,
    },
    timeout=BATCH_TIMEOUT_SEC,
)
def batch(args: argparse.Namespace) -> None:
    from .batch import handle as _handle_batch

    # NOTE!: get client on remote for OIDC
    _handle_batch(_sanitize_args(args), s3=_s3_client())


def handle_batch(args: argparse.Namespace) -> None:
    with app.run():
        batch.remote(args)


def command(parser: argparse.ArgumentParser) -> argparse.Namespace:

    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    parser = subparsers.add_parser("test", help="Test modal")
    parser.add_argument("--value", type=int, required=True)
    parser.set_defaults(func=handle_test)

    parser = subparsers.add_parser("eval", help="Evaluate on modal")
    eval_command(parser)
    parser.set_defaults(func=handle_eval)

    parser = subparsers.add_parser("batch", help="Batch on modal")
    batch_command(parser)
    parser.set_defaults(func=handle_batch)

    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main():
    args = cli()
    args.func(args)
