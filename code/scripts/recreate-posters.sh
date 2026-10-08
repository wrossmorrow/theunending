#!/bin/bash

set -ex
# set -a && source .env && set +a

# define these

POST_TITLE="Paiters Block"
POST_DATE="2026-10-07"
SET_NAME="painters-block"

# let it rip below here

# infer vars (ok, some defined, but still)

SITE_BUCKET="theunending-ai-site-content-use1"
POST_NAME="${POST_DATE}-${SET_NAME}"
SITE_IMG_ASSETS="s3://${SITE_BUCKET}/assets/img/${POST_NAME}/"

PROMPT_HASH=$( echo -n "${PROMPT}" | sha256sum | cut -d ' ' -f 1 )
RAW_BUCKET="wrossmorrow-genai-repetitions-use1"
RAW_PREFIX="runs/${PROMPT_HASH}"

PORTRAIT_SIZES=( "12x18" "18x24" "24x36" "36x48" )
LANDSCAPE_SIZES=( "40x80" )

# create OG image

# "${HOME}/.venv/bin/python" "${HOME}/og_tiles.py" \
#     --set "${SET_NAME}" \
#     --prefix "${RAW_PREFIX}" \
#     --source ./images \
#     --out og

# aws s3 cp "og/${SET_NAME}.jpg" "s3://${SITE_BUCKET}/assets/og/${SET_NAME}.jpg"

# create posters

for SIZE in "${PORTRAIT_SIZES[@]}"; do
    OUTPUT_NAME="posters/${SIZE}/${POST_NAME}.png"
    mkdir -p "posters/${SIZE}"
    uv run python poster.py \
        --poster "${SIZE}" \
        --orientation portrait \
        --dpi 150 \
        --tile 1.5 \
        --title "${POST_TITLE}" \
        "${SITE_IMG_ASSETS}" \
        ${OUTPUT_NAME}
    aws s3 cp "${OUTPUT_NAME}" "s3://${SITE_BUCKET}/assets/img/posters/raw/${POST_NAME}/${SIZE}.png"
done
for SIZE in "${LANDSCAPE_SIZES[@]}"; do
    OUTPUT_NAME="posters/${SIZE}/${POST_NAME}.png"
    mkdir -p "posters/${SIZE}"
    uv run python poster.py \
        --poster "${SIZE}" \
        --orientation landscape \
        --dpi 150 \
        --tile 1.5 \
        --title "${POST_TITLE}" \
        "${SITE_IMG_ASSETS}" \
        ${OUTPUT_NAME}
    aws s3 cp "${OUTPUT_NAME}" "s3://${SITE_BUCKET}/assets/img/posters/raw/${POST_NAME}/${SIZE}.png"
done

# webp's for poster printable page

uv run python web-posters.py posters
