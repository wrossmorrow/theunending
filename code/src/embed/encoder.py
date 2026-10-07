"""Local image embeddings from Meta's Perception Encoder (PE Core).

Runs entirely on-device: PyTorch + open_clip, using Apple Silicon's MPS
backend when it is available. Weights are pulled from the Hugging Face hub
on first use and cached under ~/.cache/huggingface.
"""

from __future__ import annotations

import os

# Must be set before any MPS kernel dispatch; a few ops still lack Metal
# implementations and silently need the CPU fallback.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

import numpy as np
import torch
from PIL import Image

__all__ = [
    "MODELS",
    "IMAGE_EXTENSIONS",
    "PEEncoder",
    "iter_images",
    "pick_device",
    "resolve_model",
]

# Short name -> Hugging Face repo. These are the OpenCLIP-remapped PE Core
# checkpoints; `encode_image` on them returns the contrastive (CLIP-space)
# embedding, which is what you want for similarity and retrieval.
MODELS: dict[str, str] = {
    "T": "hf-hub:timm/PE-Core-T-16-384",
    "S": "hf-hub:timm/PE-Core-S-16-384",
    "B": "hf-hub:timm/PE-Core-B-16",
    "L": "hf-hub:timm/PE-Core-L-14-336",
    "bigG": "hf-hub:timm/PE-Core-bigG-14-448",
}

DEFAULT_MODEL = "L"

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}

DTYPES: dict[str, torch.dtype] = {
    "float32": torch.float32,
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
}


def resolve_model(name: str) -> str:
    """Map a short name (L, bigG, ...) or a hub id to an open_clip model id."""
    if name in MODELS:
        return MODELS[name]
    if name.startswith("hf-hub:"):
        return name
    if "/" in name:
        return f"hf-hub:{name}"
    raise ValueError(
        f"Unknown model {name!r}. Use one of {', '.join(MODELS)} "
        "or a Hugging Face repo id."
    )


def pick_device(preference: str = "auto") -> torch.device:
    """Resolve the torch device, preferring Apple Silicon's MPS backend."""
    if preference not in {"auto", "mps", "cpu", "cuda"}:
        raise ValueError(f"Unknown device {preference!r}")
    if preference != "auto":
        return torch.device(preference)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def iter_images(paths: Iterable[str | Path], recursive: bool = True) -> list[Path]:
    """Expand files and directories into a sorted list of image paths."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            walker = path.rglob("*") if recursive else path.glob("*")
            found.extend(
                p
                for p in walker
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
            )
        elif path.is_file():
            found.append(path)
        else:
            raise FileNotFoundError(path)
    # Deduplicate while keeping a stable, reproducible order.
    return sorted({p.resolve() for p in found})


def _batched(items: Sequence[Path], size: int) -> Iterator[Sequence[Path]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


@dataclass
class PEEncoder:
    """A loaded PE Core vision encoder.

    Example:
        enc = PEEncoder.load("L")
        vectors = enc.embed(["photo.jpg"])   # (1, 1024) float32, L2-normalized
    """

    model: object
    preprocess: object
    device: torch.device
    dtype: torch.dtype
    model_id: str
    image_size: int = 0
    _dim: int = field(default=0, repr=False)

    @classmethod
    def load(
        cls,
        model: str = DEFAULT_MODEL,
        device: str = "auto",
        dtype: str = "float32",
    ) -> "PEEncoder":
        import open_clip  # imported lazily so `--help` stays fast

        model_id = resolve_model(model)
        torch_device = pick_device(device)
        torch_dtype = DTYPES[dtype]

        net, _, preprocess = open_clip.create_model_and_transforms(model_id)
        net.eval()
        net.to(device=torch_device, dtype=torch_dtype)
        for param in net.parameters():
            param.requires_grad_(False)

        image_size = getattr(net.visual, "image_size", 0)
        if isinstance(image_size, (tuple, list)):
            image_size = image_size[0]

        return cls(
            model=net,
            preprocess=preprocess,
            device=torch_device,
            dtype=torch_dtype,
            model_id=model_id,
            image_size=int(image_size or 0),
        )

    @property
    def dim(self) -> int:
        """Embedding dimensionality (1024 for T/S/B/L, 1280 for bigG)."""
        if not self._dim:
            self._dim = self.embed_pil([Image.new("RGB", (64, 64))]).shape[1]
        return self._dim

    def embed_pil(
        self, images: Sequence[Image.Image], normalize: bool = True
    ) -> np.ndarray:
        """Embed already-opened PIL images. Returns (N, D) float32."""
        tensors = [self.preprocess(img.convert("RGB")) for img in images]
        batch = torch.stack(tensors).to(device=self.device, dtype=self.dtype)
        with torch.inference_mode():
            features = self.model.encode_image(batch, normalize=normalize)
        return features.float().cpu().numpy()

    def embed(
        self,
        paths: Sequence[str | Path],
        batch_size: int = 8,
        normalize: bool = True,
        on_batch=None,
    ) -> np.ndarray:
        """Embed image files. Returns (N, D) float32 in the order given."""
        resolved = [Path(p) for p in paths]
        chunks: list[np.ndarray] = []
        done = 0
        for batch in _batched(resolved, batch_size):
            images = [Image.open(p) for p in batch]
            try:
                chunks.append(self.embed_pil(images, normalize=normalize))
            finally:
                for img in images:
                    img.close()
            done += len(batch)
            if on_batch is not None:
                on_batch(done, len(resolved))
        if not chunks:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.concatenate(chunks, axis=0)
