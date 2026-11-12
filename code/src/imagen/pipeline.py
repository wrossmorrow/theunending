from __future__ import annotations

from collections.abc import Callable

import torch
from diffusers import (
    ComponentsManager,
    Flux2KleinPipeline,
    Flux3ModularPipeline,
    FluxPipeline,
    ModularPipeline,
)

from .constants import DEVICE, TORCH_DTYPE

# TODO; decent typing of the pipeline

SomePipeline = FluxPipeline | Flux2KleinPipeline | ModularPipeline

DISTILLED_KLEIN_STEPS = 4
FLUX3_STEPS = 16


def normalized_model_id(model_id: str) -> str:
    """Normalize a model id for family matching (lowercase, alphanumeric only)."""
    return "".join(character for character in model_id.lower() if character.isalnum())


def default_steps_for(model_id: str) -> int:
    """Default inference steps for a model: flux3 is calibrated for 16, distilled klein for 4."""
    return (
        FLUX3_STEPS
        if "flux3" in normalized_model_id(model_id)
        else DISTILLED_KLEIN_STEPS
    )


def load_pipeline(model_id: str) -> Callable:
    normalized = normalized_model_id(model_id)

    if "flux3" in normalized:
        manager = ComponentsManager()
        manager.enable_auto_cpu_offload(device=DEVICE)
        pipe = Flux3ModularPipeline.from_pretrained(
            model_id,
            components_manager=manager,
        )
        pipe.load_components(
            local_files_only=True, dtype={"vae": torch.float32, "default": TORCH_DTYPE}
        )

        upsampler = getattr(pipe, "prompt_upsampler", None)
        upsampler_processor = getattr(pipe, "prompt_upsampler_processor", None)
        transformer = getattr(pipe, "transformer", None)
        if upsampler is None or upsampler_processor is None or transformer is None:
            raise RuntimeError(
                f"Failed to load FLUX.3 components for {model_id}: "
                f"prompt_upsampler={upsampler is not None}, "
                f"prompt_upsampler_processor={upsampler_processor is not None}, "
                f"transformer={transformer is not None}"
            )

        pipe = pipe.to(DEVICE)
        return pipe

    if "flux1" in normalized:
        pipe = FluxPipeline.from_pretrained(
            model_id,
            torch_dtype=TORCH_DTYPE,
        )
    else:
        pipe = Flux2KleinPipeline.from_pretrained(
            model_id,
            torch_dtype=TORCH_DTYPE,
        )

    # Enable VRAM optimizations if running on consumer hardware
    if DEVICE == "cuda":
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        if vram_gb < 20:
            print(f"{vram_gb:.1f} GB VRAM: using CPU offload")
            pipe.enable_model_cpu_offload()
        else:
            print(f"{vram_gb:.1f} GB VRAM: full model on GPU")
            pipe.to(DEVICE)
    else:
        pipe.to(DEVICE)

    return pipe
