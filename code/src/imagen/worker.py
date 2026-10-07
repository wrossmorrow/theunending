import argparse
import io
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence
from uuid import uuid4
import random

import boto3
import torch
from diffusers import FluxPipeline, Flux2KleinPipeline


DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
TORCH_DTYPE = torch.bfloat16 if DEVICE in ("cuda", "mps") else torch.float32


s3 = boto3.client("s3")
pool = ThreadPoolExecutor(max_workers=8)


def load_pipeline(model_id):
    pipe = (
        FluxPipeline.from_pretrained(
            model_id,
            torch_dtype=TORCH_DTYPE,
        )
        if "FLUX.1" in model_id else
        Flux2KleinPipeline.from_pretrained(
            model_id,
            torch_dtype=TORCH_DTYPE,
        )
    ).to("cuda")
    return pipe


def upload_buffer(buf: bytes, format: str, s3_bucket: str, s3_key: str, metadata: dict):
    s3.put_object(
        Bucket=s3_bucket,
        Key=s3_key,
        Body=buf,
        ContentType=f"image/{format.lower()}",
        Metadata=metadata,
    )


def count_s3_prefix_objects(bucket: str, prefix: str, suffix: str | Sequence[str] | None = ".png") -> int:
    # Ensure prefix ends with a slash if targeting a "folder"
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    # Normalize suffix into a tuple so str.endswith() can check single or multiple extensions
    if isinstance(suffix, str):
        suffix = (suffix,)
    elif suffix is not None:
        suffix = tuple(suffix)

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    total_count = 0
    for page in pages:
        if suffix is None:
            total_count += page.get("KeyCount", 0)
        else:
            contents = page.get("Contents", [])
            total_count += sum(1 for obj in contents if obj["Key"].endswith(suffix))

    return total_count


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--s3-bucket", type=str, required=True)
    parser.add_argument("--s3-prefix", type=str, required=True)
    parser.add_argument("--max-images", type=int, default=5_000)
    parser.add_argument("--format", type=str, default="PNG")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--outdir", type=str, default="images")
    parser.add_argument("--model-id", type=str, default="black-forest-labs/FLUX.2-klein-4B")

    args = parser.parse_args()

    existing = count_s3_prefix_objects(args.s3_bucket, args.s3_prefix)
    total = args.max_images - existing

    print(f"Progress: {existing}/{args.max_images} already exist; work on {total}.")

    pipe = load_pipeline(args.model_id)

    chopped_prompt = args.prompt[:120]

    for idx in range(total):

        seed = random.randint(0, 2**32 - 1)

        gen = torch.Generator(device="cuda").manual_seed(seed)
        image = pipe(
            prompt=args.prompt,
            num_inference_steps=args.steps,
            generator=gen,
            height=args.height,
            width=args.width,
        ).images[0]

        buf = io.BytesIO()
        image.save(buf, format=args.format, optimize=True)
        raw_bytes = buf.getvalue()

        image_id = uuid4()

        # we could store local here too, embed if we load an embedder, 
        # "extend" a numpy array, track UUIDs, and on and on. in any case, 
        # storing locally would be a good start. other codes can use data
        # on disk already.
        filename = f"{args.outdir}/{image_id}.png"
        with open(filename, "wb") as f:
            f.write(buf.getbuffer())

        s3_key = f"{args.s3_prefix}/{image_id}.png"
        pool.submit(
            upload_buffer,
            raw_bytes,
            args.format,
            args.s3_bucket,
            s3_key,
            {
                "seed": str(seed),
                "prompt": chopped_prompt,
            },
        )

        if (idx + 1) % 50 == 0 or (idx + 1) == total:
            print(f"Progress: [{idx + 1}/{total}] generated and queued.")

    pool.shutdown(wait=True)
    print("All tasks finished and synced to S3.")


if __name__ == "__main__":
    main()
