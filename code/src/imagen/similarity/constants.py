import torch

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
