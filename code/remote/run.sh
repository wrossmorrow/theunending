#!/bin/bash

set -ex
set -a
source .env
source .run
set +a

for V in POST_TITLE SET_NAME PROMPT; do
    if [[ -z "${!V}" ]]; then
        echo "${V} is not set or empty" >&2
        exit 1
    fi
done

# infer vars (ok, some defined, but still)

DEFAULT_MODEL_ID="black-forest-labs/FLUX.2-klein-4B" 
if [[ -z "${MODEL_ID}" ]]; then
    echo "MODEL_ID is not set or empty: ${MODEL_ID}; defaulting to ${DEFAULT_MODEL_ID}"
    MODEL_ID="${DEFAULT_MODEL_ID}"
fi

DEFAULT_SITE_BUCKET="theunending-ai-site-content-use1"
DEFAULT_RAW_BUCKET="wrossmorrow-genai-repetitions-use1"

SITE_BUCKET="${SITE_BUCKET:-$DEFAULT_SITE_BUCKET}"
POST_DATE="$( TZ="America/Los_Angeles" date +%Y-%m-%d )"
POST_NAME="${POST_DATE}-${SET_NAME}"
SITE_IMG_ASSETS="s3://${SITE_BUCKET}/assets/img/${POST_NAME}/"

PROMPT_HASH=$( echo -n "${PROMPT}" | sha256sum | cut -d ' ' -f 1 )
RAW_BUCKET="${RAW_BUCKET:-$DEFAULT_RAW_BUCKET}"
RAW_PREFIX="runs/${PROMPT_HASH}"

SITE_OG_IMAGE_PREFIX="s3://${SITE_BUCKET}/assets/og"
SITE_POSTER_RAW_PREFIX="s3://${SITE_BUCKET}/assets/img/posters/raw"
SITE_POSTER_PREVIEW_PREFIX="s3://${SITE_BUCKET}/assets/img/posters/previews"
SITE_POSTER_THUMBS_PREFIX="s3://${SITE_BUCKET}/assets/img/posters/thumbs"

PYTHON_EXE="${HOME}/.venv/bin/python"

declare -A POSTER_SIZES=(
    ["12x18"]="portrait"
    ["18x24"]="portrait"
    ["24x36"]="portrait"
    ["36x48"]="portrait" 
    ["40x80"]="landscape"
)

# setup

mkdir -p "images" "similar" "posters" "og"

# NOTE: check/gate is still valuable, but code may do this now
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
categories: [unending]
set: ${SET_NAME}
image: assets/og/${SET_NAME}.jpg
---

{% include image-stream.html set=page.set cols=5 rows=6 interval=500 %}

---

<small>Created with [${MODEL_ID}](https://huggingface.co/${MODEL_ID}). Similarities in modals define by embeddings from [perception encoder](https://huggingface.co/facebook/PE-Core-L14-336). All computed on an A100 instance in lambda labs.</small>
EOF

# EXECUTE!!!!!!

# make the images

# uv run python src/imagen/cspworker.py \
uv run imagen batch \
    --prompt "${PROMPT}" \
    --s3-bucket "${RAW_BUCKET}" \
    --s3-prefix "${RAW_PREFIX}" \
    --model-id "${MODEL_ID}" \
    --outdir images

# embed for similar images

uv run imagen similarity embed --batch-size 16 --out embeddings.npy images
uv run imagen similarity review --input embeddings.npy --output similar

aws s3 sync images/ "${SITE_IMG_ASSETS}" --exclude "*" --include "*.png"
aws s3 sync similar/ "${SITE_IMG_ASSETS}" --exclude "*" --include "*.json"

aws s3 ls "${SITE_IMG_ASSETS}" \
    | awk '{ print $4 }' | grep '\.png$' | sed 's/\.png$//' \
    | uv run python -c 'import sys,json; json.dump([l.strip() for l in sys.stdin if l.strip()], sys.stdout)' \
    > ${SET_NAME}.json

# create OG image, upload to S3

uv run imagen og-tiles \
    --set "${SET_NAME}" \
    --prefix "${RAW_PREFIX}" \
    --source ./images \
    --out og

aws s3 cp "og/${SET_NAME}.jpg" "${SITE_OG_IMAGE_PREFIX}/${SET_NAME}.jpg"

# create posters, upload raw to S3

for SIZE in "${!POSTER_SIZES[@]}"; do
    OUTPUT_NAME="posters/${SIZE}/${POST_NAME}.png"
    ORIENTATION="${POSTER_SIZES[${SIZE}]}"
    if [ ! -f "${OUTPUT_NAME}" ]; then
        mkdir -p "posters/${SIZE}"
        uv run imagen full-posters \
            --poster "${SIZE}" \
            --orientation "${ORIENTATION}" \
            --dpi 150 \
            --tile 1.5 \
            --title "${POST_TITLE}" \
            "${SITE_IMG_ASSETS}" \
            ${OUTPUT_NAME}
        aws s3 cp "${OUTPUT_NAME}" "${SITE_POSTER_RAW_PREFIX}/${POST_NAME}/${SIZE}.png"
    fi
done

# webp's for poster printable page, upload previews and thumbs to s3

uv run imagen web-posters posters
aws s3 cp \
    "posters/previews/${POST_DATE}-${SET_NAME}/" \
    "${SITE_POSTER_PREVIEW_PREFIX}/${POST_DATE}-${SET_NAME}/" \
    --recursive --exclude "*" --include "*.webp"
aws s3 cp \
    "posters/thumbs/${POST_DATE}-${SET_NAME}/" \
    "${SITE_POSTER_THUMBS_PREFIX}/${POST_DATE}-${SET_NAME}/" \
    --recursive --exclude "*" --include "*.webp"
