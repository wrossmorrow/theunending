"""Prompt helpers for the Unending Admin API."""

import hashlib


def compute_model_prompt_hash(model: str, prompt: str) -> str:
    """Compute the model prompt hash: sha256(model::prompt)."""
    return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()
