#!/bin/bash

set -ex
set -a && source .env && set +a

# define these

# POST_TITLE="Emo Vermeer"
# SET_NAME="emo-pearl"
# MODEL_ID="black-forest-labs/FLUX.2-klein-4B"
# PROMPT="an emo woman with a pearl earring, yellow headband. painting, reminiscent of the vermeer but modern hyperrealistic painting. shadowy, chiaroscuro style"

# POST_TITLE="Calavaras"
# SET_NAME="cardboard-calavaras"
# MODEL_ID="black-forest-labs/FLUX.2-klein-4B"
# PROMPT="a painting of a calavaras (a colorful, intricately designed skull); thickly applied paint; colorful. painted directly on a cardboard square"

# POST_TITLE="Load Bearing"
# SET_NAME="load-bearing"
# MODEL_ID="black-forest-labs/FLUX.2-klein-4B"
# PROMPT="a photograph taken from behind a gallery wall. raw plywood, aluminum brackets, and bundled cable runs held with zip ties, lit by a single clamped work light. bright white light leaks around every edge of the panel from the exhibition on the other side, and a thin rectangle of that light falls across the concrete floor. nothing on this side is finished or painted. 35mm, shallow depth of field, cool shadows against the warm spill, quiet and unglamorous."

POST_TITLE="Attention"
SET_NAME="attention"
MODEL_ID="black-forest-labs/FLUX.2-klein-4B"
PROMPT="an iphone photograph of a large mass of people in an art gallery staring at a painting. we can barely see the painting there are so many crowded people. some are taking pictures themselves of the painting. another painting sits to side alone, with no attention."

# POST_TITLE="Gentrification"
# SET_NAME="gentrification"
# MODEL_ID="black-forest-labs/FLUX.2-klein-4B"
# PROMPT="an iphone photograph of a an empty in-wall case in a museum. the case is embedded in the wall with clear facing glass in which we can see some reflections of lights and people. there are interior lighst in the case casting uneven light and shadows emphasizing the rectangular geometry. blocky, rectangular white stands sit in the case waiting for pieces to be displayed. the case walls are a constrasting primary color. the walls outside the case are a boring neutral grey color"

# let it rip below here

# infer vars (ok, some defined, but still)

SITE_BUCKET="theunending-ai-site-content-use1"
POST_DATE="$( date -d 'TZ="America/Los_Angeles"' -I )"
POST_NAME="${POST_DATE}-${SET_NAME}"
SITE_IMG_ASSETS="s3://${SITE_BUCKET}/assets/img/${POST_NAME}/"

PROMPT_HASH=$( echo -n "${PROMPT}" | sha256sum | cut -d ' ' -f 1 )
RAW_BUCKET="wrossmorrow-genai-repetitions-use1"
RAW_PREFIX="runs/${PROMPT_HASH}"

declare -A POSTER_SIZES=(
    ["12x18"]="portrait"
    ["18x24"]="portrait"
    ["24x36"]="portrait"
    ["36x48"]="portrait" 
    ["40x80"]="landscape"
)

# setup

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
    --prefix "${RAW_PREFIX}" \
    --source ./images \
    --out og

aws s3 cp "og/${SET_NAME}.jpg" "s3://${SITE_BUCKET}/assets/og/${SET_NAME}.jpg"

# create posters

for SIZE in "${!POSTER_SIZES[@]}"; do
    OUTPUT_NAME="posters/${SIZE}/${POST_NAME}.png"
    ORIENTATION="${POSTER_SIZES[${SIZE}]}"
    if [ ! -f "${OUTPUT_NAME}" ]; then
        mkdir -p "posters/${SIZE}"
        uv run python poster.py \
            --poster "${SIZE}" \
            --orientation "${ORIENTATION}" \
            --dpi 150 \
            --tile 1.5 \
            --title "${POST_TITLE}" \
            "${SITE_IMG_ASSETS}" \
            ${OUTPUT_NAME}
        aws s3 cp "${OUTPUT_NAME}" "s3://${SITE_BUCKET}/assets/img/posters/raw/${POST_NAME}/${SIZE}.png"
    fi
done

# webp's for poster printable page

uv run python web-posters.py posters
