"""Local image embeddings from Meta's Perception Encoder (PE Core)."""

from .encoder import MODELS, PEEncoder, iter_images, pick_device, resolve_model

__all__ = ["MODELS", "PEEncoder", "iter_images", "pick_device", "resolve_model", "main"]
__version__ = "0.1.0"


def main() -> int:
    from .cli import main as _main

    return _main()
