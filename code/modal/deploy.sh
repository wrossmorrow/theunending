#!/bin/bash
uv run python modal/image.py
uv run modal deploy -m src.imagen.modal
uv run modal deploy modal/api.py
