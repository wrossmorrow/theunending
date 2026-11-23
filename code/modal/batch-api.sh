#!/bin/bash
# Trigger a Modal batch job via the public entrypoint.
# Uses a pre-minted GOOGLE_MACHINE_ID_TOKEN if set, or impersonates
# GCP_SERVICE_ACCOUNT_EMAIL via gcloud (no static service account keys).
set -euo pipefail

: "${PROMPT:?}" "${S3_PREFIX:?}"

MODAL_ENDPOINT=https://morrowwr--theunending-api-entrypoint.us-east.modal.run
AUDIENCE="${MODAL_API_AUDIENCE:-${ADMIN_API_AUDIENCE:-https://admin.theunending.ai}}"

if [ -n "${GOOGLE_MACHINE_ID_TOKEN:-}" ]; then
    TOKEN="${GOOGLE_MACHINE_ID_TOKEN}"
else
    : "${GCP_SERVICE_ACCOUNT_EMAIL:?Set GCP_SERVICE_ACCOUNT_EMAIL or GOOGLE_MACHINE_ID_TOKEN}"
    TOKEN=$(gcloud auth print-identity-token \
        --impersonate-service-account="${GCP_SERVICE_ACCOUNT_EMAIL}" \
        --audiences="${AUDIENCE}")
fi

BODY=$(jq -nc --arg prompt "$PROMPT" --arg s3_prefix "$S3_PREFIX" \
    '{prompt: $prompt, s3_prefix: $s3_prefix}')

curl -X POST "${MODAL_ENDPOINT}/batch" \
    -H 'content-type: application/json' \
    -H 'accept: application/json' \
    -H 'authorization: Bearer '"${TOKEN}" \
    -d "${BODY}" \
    -s | jq .
