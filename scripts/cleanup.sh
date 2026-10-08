#!/bin/bash

BUCKET="theunending-ai-site-content-use1"
PREFIX="assets/img/2026-10-07-painters-block/"

comm -23 \
  <( aws s3api list-objects-v2 \
      --bucket "$BUCKET" \
      --prefix "$PREFIX" \
      --query 'Contents[].Key' \
      --output text | tr '\t' '\n' | \
      grep -E '\.(png|json)$' | \
      sort ) \
  <( awk '{ print "'"$PREFIX"'" $0 ".png\n" "'"$PREFIX"'" $0 ".json"}' ids.txt | sort ) \
  > to_delete.txt

cat to_delete.txt | xargs -n 1000 bash -c '
  keys=("$@")
  json_payload=$(printf "%s\n" "${keys[@]}" | jq -R . | jq -s "{Objects: map({Key: .}), Quiet: true}")
  aws s3api delete-objects --bucket "'"$BUCKET"'" --delete "$json_payload"
' _
