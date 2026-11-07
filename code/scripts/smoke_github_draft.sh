#!/bin/bash

: ${RUN_ID:?}

set -a \
    && source .env \
    && source secret/.env \
    && set +a

uv run python scripts/smoke_github_draft.py
