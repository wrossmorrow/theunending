#!/bin/bash

DEFAULT_SITE_BUCKET="theunending-ai-site-content-use1"
DEFAULT_RAW_BUCKET="wrossmorrow-genai-repetitions-use1"
DEFAULT_ADMIN_API_HOST="https://admin.theunending.ai"

: ${BATCH_RUN_ID:?} ${ADMIN_API_TOKEN:?}

# (I don't really like this, but it could mostly work)
# Set the values of the 

ADMIN_API_HOST=${ADMIN_API_HOST:-$DEFAULT_ADMIN_API_HOST}

HTTP_STATUS=$( curl "${ADMIN_API_HOST}/api/v0/runs/${BATCH_RUN_ID}" -H 'authorization: '${ADMIN_API_TOKEN} -H 'accept: application/json' -s -o get-run.json -w "%{http_code}" )
if [ "${HTTP_STATUS}" -ne 200 ]; then
    RESPONSE=$( cat get-run.json )
    echo "GET ${ADMIN_API_HOST}/api/v0/runs/${BATCH_RUN_ID} returned ${HTTP_STATUS} (${RESPONSE})" >&2
    exit 1
fi

RUN_TYPE=$( cat get-run.json | jq -r .type )
if [ "${RUN_TYPE}" -ne "BATCH" ]; then
    RESPONSE=$( cat get-run.json | jq -c . )
    echo "Run passed (${BATCH_RUN_ID}) is not a BATCH run (${RESPONSE})" >&2
    exit 1
fi

RUN_STATUS=$( cat get-run.json | jq -r .status )
if [ "${RUN_STATUS}" -ne "COMPLETED" ]; then
    RESPONSE=$( cat get-run.json | jq -c . )
    echo "Run passed (${BATCH_RUN_ID}) is not COMPLETED (${RESPONSE})" >&2
    exit 1
fi

SET_ID=$( cat get-run.json | jq -r .set_id )

HTTP_STATUS=$( curl "${ADMIN_API_HOST}/api/v0/sets/${SET_ID}" -H 'authorization: '${ADMIN_API_TOKEN} -H 'accept: application/json' -s -o get-set.json -w "%{http_code}" )
if [ "${HTTP_STATUS}" -ne 200 ]; then
    RESPONSE=$( cat get-set.json )
    echo "GET ${ADMIN_API_HOST}/api/v0/runs/${BATCH_RUN_ID} returned ${HTTP_STATUS} (${RESPONSE})" >&2
    exit 1
fi

MODEL_ID=$( cat get-set.json | jq -r .model )
PROMPT=$( cat get-set.json | jq -r .prompt )
MODEL_PROMPT_HASH=$( cat get-set.json | jq -r .model_prompt_hash )
SET_NAME=$( cat get-set.json | jq -r .slug )
POST_TITLE=$( cat get-set.json | jq -r .name )

# validate the key items here

for V in POST_TITLE SET_NAME PROMPT; do
    if [[ -z "${!V}" ]]; then
        echo "${V} is not set or empty" >&2
        exit 1
    fi
done

# infer vars (ok, some defined, but still)

DEFAULT_MODEL_ID="black-forest-labs/flux-3-image-klein" 
if [[ -z "${MODEL_ID}" ]]; then
    echo "MODEL_ID is not set or empty: ${MODEL_ID}; defaulting to ${DEFAULT_MODEL_ID}"
    MODEL_ID="${DEFAULT_MODEL_ID}"
fi

SITE_BUCKET="${SITE_BUCKET:-$DEFAULT_SITE_BUCKET}"
POST_DATE="$( TZ="America/Los_Angeles" date +%Y-%m-%d )"
POST_NAME="${POST_DATE}-${SET_NAME}"
SITE_IMG_ASSETS="s3://${SITE_BUCKET}/assets/img/${POST_NAME}/"

DEFAULT_PROMPT_HASH=$( python3 -c "import os, hashlib; v = \"${MODEL_ID}::${PROMPT}\"; hash = hashlib.sha256(v.encode()).hexdigest(); print(hash, end='')" )
PROMPT_HASH=${MODEL_PROMPT_HASH:-$DEFAULT_PROMPT_HASH}

RAW_BUCKET="${RAW_BUCKET:-$DEFAULT_RAW_BUCKET}"
RAW_PREFIX="runs/${PROMPT_HASH}"
RAW_IMG_ASSETS="s3://${RAW_BUCKET}/${RAW_PREFIX}"

SITE_OG_IMAGE_PREFIX="s3://${SITE_BUCKET}/assets/og"
SITE_POSTER_RAW_PREFIX="s3://${SITE_BUCKET}/assets/img/posters/raw"
SITE_POSTER_PREVIEW_PREFIX="s3://${SITE_BUCKET}/assets/img/posters/previews"
SITE_POSTER_THUMBS_PREFIX="s3://${SITE_BUCKET}/assets/img/posters/thumbs"

echo "Finishing run:"
echo "  From s3://${RAW_BUCKET}/${RAW_PREFIX}"
echo "    To ${SITE_IMG_ASSETS} (and more)"

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

# NOTE: check/gate is still valuable, but code may do this now...

# get all the raw content locally

aws s3 cp "${RAW_IMG_ASSETS}" images --recursive --exclude "*" --include "*.png"
aws s3 cp "${RAW_IMG_ASSETS}/embeddings.npy" embeddings.npy
aws s3 cp "${RAW_IMG_ASSETS}/embeddings.npy.json" embeddings.npy.json

# do the embeddings review, creating similarity jsons

uv run embed review --input embeddings.npy --output similar

# upload to the site bucket

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

# post file

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


