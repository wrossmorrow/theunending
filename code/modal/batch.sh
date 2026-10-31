#!/bin/bash
: ${PROMPT:?}

PROMPT_HASH=$( echo -n "${PROMPT}" | sha256sum | cut -d ' ' -f 1 )
echo "prompt hash (s3 prefix): ${PROMPT_HASH}"

uv run imagen modal batch \
  --s3-bucket wrossmorrow-genai-repetitions-use1 \
  --s3-prefix "runs/${PROMPT_HASH}" \
  --prompt "${PROMPT}" \
  --max-images 100
