#!/usr/bin/env bash
#
# Regenerate the per-set image id lists from S3.
#
# Three things the earlier version tripped on:
#  - `declare -A` needs bash 4+; macOS ships bash 3.2, where [key]=value is
#    read as an arithmetic subscript and `set -u` reports "unbound variable".
#    So: a plain list of "key<TAB>prefix" lines, which works anywhere.
#  - `grep` exits 1 when nothing matches, which under `set -e -o pipefail`
#    kills the script. A set with no PNGs is a normal state here (metadata
#    uploaded, images not yet), so the filtering happens in python instead.
#  - `>` truncates before the pipeline runs, so a failure mid-pipeline leaves
#    an empty file. Writes land in a temp file and move into place on success.

set -euo pipefail

BUCKET="s3://theunending-ai-site-content-use1/assets/img"
OUTDIR="${OUTDIR:-_data/stream_ids}"   # OUTDIR=assets/streams ./regen... to write manifests directly

# key                     prefix
SOURCES="
computation               2026-09-12-computation
pearl-earring             2026-09-12-pearl-earring
memento-mori              2026-09-12-memento-mori
dumpster-fire             2026-09-27-dumpster-fire
news-profile              2026-09-27-news-profile
lake-water                2026-09-27-lake-water
modern-painting           2026-09-27-modern-painting
old-computers             2026-09-27-old-computers
obsolete-masters          2026-09-27-obsolete-masters
masks                     2026-09-27-masks
dress-code                2026-09-27-dress-code
sci-fi                    2026-09-30-sci-fi
framed                    2026-09-30-framed
icee                      2026-09-30-icee
grocery-shopping          2026-09-30-grocery-shopping
black-holes               2026-10-01-black-holes
burnt-sockets             2026-10-02-burnt-sockets
tombstone                 2026-10-02-tombstone
drip-pope                 2026-10-02-drip-pope
desert-rocks              2026-10-02-desert-rocks
health-food               2026-10-02-health-food
invisible-tanks           2026-10-03-invisible-tanks
modern-painting-flux2     2026-10-05-modern-painting
cloud-outline             2026-10-05-cloud-outline
"

mkdir -p "$OUTDIR"
empty=""

while read -r KEY PREFIX; do
    [ -z "${KEY}" ] && continue
    OUT="${OUTDIR}/${KEY}.json"
    TMP="$(mktemp)"

    # python filters, so "no matches" is a value rather than a failing exit code
    if ! aws s3 ls "${BUCKET}/${PREFIX}/" \
        | awk '{print $4}' \
        | python3 -c '
import sys, json
ids = sorted(n[:-4] for n in (l.strip() for l in sys.stdin) if n.endswith(".png"))
json.dump(ids, sys.stdout)
' > "$TMP"; then
        echo "FAILED  ${KEY} (${PREFIX}) -- existing file left alone" >&2
        rm -f "$TMP"
        continue
    fi

    n=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$TMP")
    if [ "$n" -eq 0 ]; then
        empty="${empty} ${KEY}"
        echo "EMPTY   ${KEY} (${PREFIX}) -- no .png objects, NOT overwriting" >&2
        rm -f "$TMP"
        continue
    fi

    mv "$TMP" "$OUT"
    printf '%-24s %6d ids\n' "$KEY" "$n"
done <<EOF
${SOURCES}
EOF

if [ -n "${empty}" ]; then
    echo >&2
    echo "sets with no images in the bucket:${empty}" >&2
fi