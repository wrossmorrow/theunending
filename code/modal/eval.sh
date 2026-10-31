#!/bin/bash
: ${PROMPT:?}

PROMPT_HASH=$( echo -n "${PROMPT}" | sha256sum | cut -d ' ' -f 1 )
echo "prompt hash (s3 prefix): ${PROMPT_HASH}"

uv run imagen modal eval \
  --s3-bucket wrossmorrow-genai-repetitions-use1 \
  --s3-prefix "drafts/${PROMPT_HASH}" \
  --prompt "${PROMPT}"
