#!/bin/bash
: ${PROMPT:?} ${MODAL_ENDPOINT_AUTH_TOKEN:?}

MODAL_ENDPOINT=https://morrowwr--theunending-api-entrypoint.us-east.modal.run

curl -X POST "${MODAL_ENDPOINT}/batch" \
    -H 'content-type: application/json' \
    -H 'accept: application/json' \
    -H 'authorization: Bearer '${MODAL_ENDPOINT_AUTH_TOKEN} \
    -d '{"prompt": "'"${PROMPT}"'"}' \
    -s | jq .
