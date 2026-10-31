import torch


DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
TORCH_DTYPE = torch.bfloat16 if DEVICE in ("cuda", "mps") else torch.float32
