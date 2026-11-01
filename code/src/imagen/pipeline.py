from __future__ import annotations

from typing import Callable

import torch
from diffusers import Flux2KleinPipeline, FluxPipeline

from .constants import DEVICE, TORCH_DTYPE

# TODO; decent typing of the pipeline

SomePipeline = FluxPipeline | Flux2KleinPipeline


def load_pipeline(model_id: str) -> Callable:
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
