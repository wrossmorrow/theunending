import json
import random

import torch
from diffusers import Flux2KleinPipeline
from diffusers.utils import load_image

# 1. Load pipeline in bfloat16
model_id = "black-forest-labs/FLUX.2-klein-4B"
device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")

pipe = Flux2KleinPipeline.from_pretrained(
    model_id,
    torch_dtype=torch.bfloat16,
)
pipe.to(device)

# Optional VRAM optimizations (uncomment if running below 16GB VRAM):
# pipe.enable_model_cpu_offload()
# pipe.vae.enable_tiling()

num_refs = 5
num_out = 10

# 3. Prompting
# Refer directly to the reference inputs (e.g., 'image 1', 'image 2')
prompt = f"""
A cinematic 35mm closeup photograph of `an emo girl with a pearl earring` 
in the style of {", ".join([f"image {i}" for i in range(1, num_refs+1)])}.
Prominent pearl earring or earrings, muted light blue and yellow headband or 
hairtie. full face visible, partial profile, eyes looking directly towards the
camera. muted unfocused shadowy background suiting a portrait photograph.
"""
print("PROMPT:", prompt)

# 2. Load reference image(s) as PIL Images
# Dimensions should ideally be multiples of 16
prefix = "/Users/wrossmorrow/Work/Projects/website/jekylled/assets/img/2022-11-01-pearl/bulk"
filenames = [
    f"tile_row{r:02d}_col{c:02d}.jpg"
    for r in range(1, 9)
    for c in range(1, 8)
]

# 4. Run Inference
# Distilled Klein is calibrated for 4 steps and guidance_scale=1.0
dfn = "images/emopearl/matches.jsonl"
with open(dfn, "w") as f:
    f.write("")
for i in range(num_out):
    seed = random.randint(0, 2**32 - 1)
    gen = torch.Generator(device=device).manual_seed(seed)
    samples = random.sample(filenames, k=num_refs)
    images = [load_image(f"{prefix}/{ifn}") for ifn in samples]
    result = pipe(
        prompt=prompt,
        image=images,
        num_inference_steps=4,
        guidance_scale=1.0,
        height=1024,
        width=1024,
        generator=gen,
    ).images[0]
    outfn = f"images/emopearl/output_{i:03d}.png"
    result.save(outfn)
    with open(dfn, "a") as f:
        f.write(json.dumps({outfn: samples}) + "\n")

# result = pipe(
#     prompt=prompt,
#     image=images,  # single PIL image or list of PIL images
#     num_inference_steps=4,
#     guidance_scale=1.0,
#     height=1200,
#     width=1200,
#     generator=generator,
# ).images[0]

# result.save("klein_reference_output.png")
