#!/bin/bash
# Trigger a Modal batch job via the public entrypoint.
# Mints a fresh machine JWT signed as the admin service account (see
# code/src/machine_auth.py) instead of using a static bearer token.
set -euo pipefail

: ${PROMPT:?} ${S3_PREFIX:?} ${GOOGLE_SERVICE_ACCOUNT_KEY_JSON:?}

MODAL_ENDPOINT=https://morrowwr--theunending-api-entrypoint.us-east.modal.run

cd "$(dirname "$0")/.."  # code/
TOKEN=$(uv run python -c "
import os
from src.machine_auth import machine_jwt
print(machine_jwt(
    os.environ['GOOGLE_SERVICE_ACCOUNT_KEY_JSON'],
    os.environ.get('ADMIN_API_AUDIENCE') or 'https://admin.theunending.ai',
))
")

BODY=$(jq -nc --arg prompt "$PROMPT" --arg s3_prefix "$S3_PREFIX" \
    '{prompt: $prompt, s3_prefix: $s3_prefix}')

curl -X POST "${MODAL_ENDPOINT}/batch" \
    -H 'content-type: application/json' \
    -H 'accept: application/json' \
    -H 'authorization: Bearer '"${TOKEN}" \
    -d "${BODY}" \
    -s | jq .
