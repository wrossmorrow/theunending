#!/bin/bash

set -ex

: ${PROMPT:?}
HASH=$( printf "%s" "${PROMPT}" | sha256sum | awk '{print $1}' )
TILES="generated-tiles/${HASH}"
MODEL_ID="${MODEL_ID:-black-forest-labs/FLUX.2-klein-4B}"
OUTDIR="${OUTDIR:-images}"
ROWS="${ROWS:-3}"
COLS="${COLS:-3}"
WIDTH="${WIDTH:-512}"
HEIGHT="${HEIGHT:-512}"

mkdir -p "${TILES}" "${OUTDIR}"
echo "{{prompt}}" > "${TILES}/prompt.txt"

HOSTNAME=$( hostname -f )

echo "[${HOSTNAME}] Prompt ${PROMPT:0:40}"
echo "[${HOSTNAME}] Using ${MODEL_ID}"
echo "[${HOSTNAME}] Writing tiles into ${TILES}"
echo "[${HOSTNAME}] Writing result into ${OUTDIR}"
uv run imagen \
    --prompt="${PROMPT}" \
    --width "${WIDTH}" \
    --height "${HEIGHT}" \
    --rows "${ROWS}" \
    --cols "${COLS}" \
    --tiles "${TILES}" \
    --model-id "${MODEL_ID}" \
    --outdir "${OUTDIR}"
