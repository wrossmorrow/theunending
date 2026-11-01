#!/bin/bash
: ${PROMPT:?}

MODEL_ID="${MODEL_ID:-black-forest-labs/FLUX.2-klein-4B}"
PROMPT_HASH=$( echo -n "${MODEL_ID}::${PROMPT}" | sha256sum | cut -d ' ' -f 1 )
echo "prompt hash (s3 prefix): ${PROMPT_HASH}"

uv run imagen modal batch \
  --s3-bucket wrossmorrow-genai-repetitions-use1 \
  --s3-prefix "runs/${PROMPT_HASH}" \
  --model-id "${MODEL_ID}" \
  --prompt "${PROMPT}" \
  --max-images 25 \
  --embed
