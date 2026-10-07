#!/bin/bash

set -ex
set -a && source .env && set +a

# define these

POST_TITLE="Painters Block"
POST_DATE="$( date -I )"
SET_NAME="painters-block"
RUN_NUMBER="26"
MODEL_ID="black-forest-labs/FLUX.2-klein-4B"
PROMPT="a closeup high resolution photograph of a blank canvas in light tan, so light it is almost white. there is a very light grey pencil sketch on the canvas, a rectangular grid covering the entire canvas and outlined fluffy clouds, unfinished. there is a prominent branching crack filled with bright gold in Kintsugi style repair in the canvas. the canvas rests on a white marble counter or table."

# let it rip below here

SITE_BUCKET="theunending-ai-site-content-use1"
POST_NAME="${POST_DATE}-${SET_NAME}"
SITE_IMG_ASSETS="s3://${SITE_BUCKET}/assets/img/${POST_NAME}/"

RAW_BUCKET="wrossmorrow-genai-repetitions-use1"
RAW_PREFIX="runs/run-${RUN_NUMBER}"

mkdir -p "images" "similar" "posters" "og"

echo "${PROMPT}" > prompt.txt
if aws s3api head-object --bucket "${RAW_BUCKET}" --key "${RAW_PREFIX}/prompt.txt" >/dev/null 2>&1; then
    aws s3 cp "s3://${RAW_BUCKET}/${RAW_PREFIX}/prompt.txt" prompt-s3.txt
    if cmp -s prompt.txt prompt-s3.txt; then
        echo "Prompt uploaded matches current prompt, can proceed."
    else
        echo "Prompt supplied does not match stored prompt, please check settings."
        exit 1
    fi
else
    aws s3 cp prompt.txt "s3://${RAW_BUCKET}/${RAW_PREFIX}/prompt.txt"
fi

cat > "${POST_NAME}.md" <<EOF
---
layout: post
title: "${POST_TITLE}"
subtitle: "${PROMPT}"
date: ${POST_DATE}
location: "Places"
categories: [unending]
set: ${SET_NAME}
image: assets/og/${SET_NAME}.jpg
---

{% include image-stream.html set=page.set cols=5 rows=6 interval=500 %}

---

<small>Created with [${MODEL_ID}](https://huggingface.co/${MODEL_ID}). Similarities in modals define by embeddings from [perception encoder](https://huggingface.co/facebook/PE-Core-L14-336). All computed on an A100 instance in lambda labs.</small>
EOF

# EXECUTE!!!!!!

"${HOME}/.venv/bin/python" "${HOME}/src/imagen/worker.py" \
    --prompt "${PROMPT}" \
    --s3-bucket "${RAW_BUCKET}" \
    --s3-prefix "${RAW_PREFIX}" \
    --model-id "${MODEL_ID}"

uv run embed embed --batch-size 16 --out embeddings.npy images
uv run embed review --input embeddings.npy --output similar

aws s3 sync images/ "${SITE_IMG_ASSETS}" --exclude "*" --include "*.png"
aws s3 sync similar/ "${SITE_IMG_ASSETS}" --exclude "*" --include "*.json"

aws s3 ls "${SITE_IMG_ASSETS}" \
    | awk '{ print $4 }' | grep '\.png$' | sed 's/\.png$//' \
    | "${HOME}/.venv/bin/python" -c 'import sys,json; json.dump([l.strip() for l in sys.stdin if l.strip()], sys.stdout)' \
    > ${SET_NAME}.json

# create OG image

"${HOME}/.venv/bin/python" "${HOME}/og_tiles.py" \
    --set "${SET_NAME}" \
    --run "${RUN_NUMBER}" \
    --source ./images \
    --out og

aws s3 cp "og/${SET_NAME}.jpg" "s3://${SITE_BUCKET}/assets/og/${SET_NAME}.jpg"

# create posters

PORTRAIT_SIZES=(
    "12x18"
    "18x24"
    "24x36"
    "36x48"
)
LANDSCAPE_SIZES=(
    "40x80"
)
for SIZE in "${PORTRAIT_SIZES[@]}"; do
    OUTPUT_NAME="posters/${SIZE}/${POST_NAME}.png"
    if [ ! -f "${OUTPUT_NAME}" ]; then
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
    fi
done
for SIZE in "${LANDSCAPE_SIZES[@]}"; do
    OUTPUT_NAME="posters/${SIZE}/${POST_NAME}.png"
    if [ ! -f "${OUTPUT_NAME}" ]; then
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
    fi
done

# TODO: web copy of posters for printable

#   posters/<WxH>/<name>.png  ->  posters/thumbs/<name>/<WxH>.webp     (<= 0.5 MB, grid tile)
#                                 posters/previews/<name>/<WxH>.webp   (<= 1 MB, click-through)
#                                 posters/web.json                     (index for the page)
#                                 posters/unending-posters.json        (restructured index for the page)

uv run python web-posters.py posters
