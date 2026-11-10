"""Prompt helpers for the Unending Admin API."""

import hashlib
import re

SET_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,126}[a-z]$")


def compute_model_prompt_hash(model: str, prompt: str) -> str:
    """Compute the model prompt hash: sha256(model::prompt)."""
    return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()


def derive_set_slug(name: str) -> str:
    """Derive a set slug from a human-supplied title, with a hash fallback.

    Prompt ideas arrive as free-form titles rather than slugs, so the slug is
    derived from the title (lowercased, non-alphanumerics folded to hyphens) and
    falls back to a deterministic hash-based slug when the derived value is too
    short or does not satisfy the slug pattern.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if len(slug) < 3 or len(slug) > 128 or not SET_SLUG_PATTERN.fullmatch(slug):
        digest = hashlib.sha256(name.strip().lower().encode("utf-8")).hexdigest()[:16]
        slug = f"prompt-{digest}"
        if not SET_SLUG_PATTERN.fullmatch(slug):
            slug = f"prompt-{digest}-draft"
    return slug
