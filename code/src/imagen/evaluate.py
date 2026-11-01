from __future__ import annotations

import argparse
import glob
import inspect
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
import torch
from diffusers import Flux2KleinPipeline, FluxPipeline
from PIL import Image

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

from .constants import DEVICE, TORCH_DTYPE
from .progress import Status, update_progress


def load_pipeline(model_id: str) -> FluxPipeline | Flux2KleinPipeline:
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
    )
    
    # Enable VRAM optimizations if running on consumer hardware
    if DEVICE == "cuda":
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        if vram_gb < 24:
            pipe.enable_model_cpu_offload()
        else:
            pipe.to(DEVICE)
    else:
        pipe.to(DEVICE)
        
    return pipe


def generate_images(pipe, prompts, img_size, steps, outdir):
    images = []
    
    print(f"Generating {len(prompts)} images...")
    for idx, prompt in enumerate(prompts):
        print(f"[{idx + 1}/{len(prompts)}] Generating: {prompt[:60]}...")
        
        # Generator with a deterministic per-item seed
        seed = 42 + idx
        generator = torch.Generator(device="cpu").manual_seed(seed)
        
        image = pipe(
            prompt=prompt,
            width=img_size["width"],
            height=img_size["height"],
            num_inference_steps=steps,
            max_sequence_length=256,
            generator=generator,
        ).images[0]
        
        tile_path = Path(outdir) / f"tile_{idx:03d}.png"
        image.save(tile_path)
        images.append(image)
        
    return images


def stitch_grid(output, images, grid_cols=None, padding=8, bg_color=(255, 255, 255)):
    total_images = len(images)
    if total_images == 0:
        return
    
    # Auto-calculate rectangular/square dimensions if not provided
    if grid_cols is None:
        grid_cols = math.ceil(math.sqrt(total_images))
    grid_rows = math.ceil(total_images / grid_cols)
    
    tile_w, tile_h = images[0].size
    
    canvas_w = (grid_cols * tile_w) + ((grid_cols + 1) * padding)
    canvas_h = (grid_rows * tile_h) + ((grid_rows + 1) * padding)
    
    grid_canvas = Image.new("RGB", (canvas_w, canvas_h), color=bg_color)
    
    for idx, img in enumerate(images):
        col = idx % grid_cols
        row = idx // grid_cols
        
        x = padding + col * (tile_w + padding)
        y = padding + row * (tile_h + padding)
        
        grid_canvas.paste(img, (x, y))
        
    grid_canvas.save(output, quality=95)
    print(f"\nFinal composite saved to {output} ({canvas_w}x{canvas_h})")


def _copy_to_s3(
    args: argparse.Namespace,
    s3: S3Client,
) -> None:
    if args.s3_bucket is None:
        return
    
    s3.put_object(
        Bucket=args.s3_bucket,
        Key=f"{args.s3_prefix}/prompt.txt",
        Body=args.prompt.encode(),
    )

    for r in range(args.repetitions):
        fn = f"thematic-grid-{r}.png"
        s3.upload_file(
            Filename=f"{args.outdir}/{fn}",
            Bucket=args.s3_bucket,
            Key=f"{args.s3_prefix}/{fn}",
        )

    for tile in glob.glob(f"{args.tiles}/*.png"):
        fn = Path(tile).name
        s3.upload_file(
            Filename=tile,
            Bucket=args.s3_bucket,
            Key=f"{args.s3_prefix}/tiles/{fn}",
        )


def handle(args: argparse.Namespace, s3: S3Client | None) -> int:

    if s3 is None:
        return handle(args, boto3.client("s3"))

    try:

        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.IN_PROGRESS,
                message="job has launched successfully",
            )

        Path(args.tiles).mkdir(parents=True, exist_ok=True)
        Path(args.outdir).mkdir(parents=True, exist_ok=True)

        img_size = {
            "width": args.width,
            "height": args.height,
        }

        pipeline = load_pipeline(args.model_id)
        for r in range(args.repetitions):
            prompts = [
                f"{args.prompt}" for _ in range(args.rows * args.cols)
            ]
            generated_tiles = generate_images(pipeline, prompts, img_size, args.steps, args.tiles)
            filename = f"{args.outdir}/thematic-grid-{r}.png"
            stitch_grid(filename, generated_tiles, grid_cols=args.cols, padding=12)

            if args.status_update_url is not None:
                update_progress(
                    url=args.status_update_url,
                    status=Status.IN_PROGRESS,
                    message=f"sample {r+1}/{args.repetitions} completed",
                )

        _copy_to_s3(args, s3)

        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.COMPLETED,
                message="image generation and s3 upload completed",
            )

    except Exception as e:  # noqa: BLE001
        frame = inspect.currentframe()
        fname = frame.f_code.co_name if frame is not None else "<unknown>"
        print(f"An error occurred in {fname}: {e.__class__.__name__} {e}")
        if args.status_update_url is not None:
            update_progress(
                url=args.status_update_url,
                status=Status.FAILED,
                message="An uncaught error occurred during processing",
                details={
                    "function_name": fname,
                    "error": str(e),
                    "error_class": e.__class__.__name__,
                    "args": {k: v for k, v in vars(args).items()}
                }
            )

        return 1

    return 0


def command(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--tiles", type=str, default="generated-tiles")
    parser.add_argument("--outdir", type=str, default="images")
    parser.add_argument("--model-id", type=str, default="black-forest-labs/FLUX.2-klein-4B")
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--s3-bucket", type=str, default=os.environ.get("AWS_S3_BUCKET_NAME"))
    parser.add_argument("--s3-prefix", type=str, default="drafts")
    parser.add_argument("--status-update-url", type=str, default=None)
    parser.set_defaults(func=handle)
    return parser


def cli() -> argparse.Namespace:
    return command(argparse.ArgumentParser()).parse_args()


def main() -> None:
    args = cli()
    args.func(args)


if __name__ == "__main__":
    main()
