#!/bin/bash

set -ex
set -a && source .env && set +a

# Install uv into ~/.cargo/bin if missing and add to PATH
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:/home/ubuntu/.cargo/bin:$PATH"

# Execute using uv, inheriting system PyTorch packages from DLAMI
uv venv --system-site-packages "${HOME}/.venv"

# Install only the missing helper libraries into it
uv pip install --python "${HOME}/.venv/bin/python" \
  numpy==1.26.4 diffusers transformers accelerate sentencepiece protobuf boto3 pillow torchvision

uv run --with huggingface_hub --with hf_transfer python -c "
import os
from huggingface_hub import snapshot_download

os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'

snapshot_download(
    repo_id='black-forest-labs/FLUX.1-schnell',
    token=os.environ['HF_TOKEN']
)
snapshot_download(
    repo_id='black-forest-labs/FLUX.2-klein-4B',
    token=os.environ['HF_TOKEN']
)
snapshot_download(
    repo_id='timm/PE-Core-L-14-336',
    token=os.environ['HF_TOKEN']
)
"
