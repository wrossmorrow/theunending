import argparse
import math
from pathlib import Path
import torch
from diffusers import FluxPipeline, Flux2KleinPipeline
from PIL import Image


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
TORCH_DTYPE = torch.bfloat16 if DEVICE in ("cuda", "mps") else torch.float32


# ---------------------------------------------------------------------------
# 1. Pipeline Initialization
# ---------------------------------------------------------------------------
def load_pipeline(model_id: str):
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
        pipe.enable_model_cpu_offload()  # Keeps VRAM usage under ~12-14 GB
    else:
        pipe.to(DEVICE)
        
    return pipe


# ---------------------------------------------------------------------------
# 2. Batch Generation
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 3. Compositing & Stitching
# ---------------------------------------------------------------------------
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


def main():

    parser = argparse.ArgumentParser()
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

    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
