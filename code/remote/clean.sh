#!/bin/bash

set -ex
set -a && source .env && set +a

rm -rf "images" "similar" "posters" "og"
rm embeddings.npy* *.md prompt*.txt *.json
