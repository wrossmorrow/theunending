#!/usr/bin/env bash
#
# Populate `thumb` for each set in _data/streams.yml from the first id in
# assets/streams/<set>.json.
#
# Four things the previous version tripped on, all verified:
#
#  - `yq ... > "$TEMP"` truncates $TEMP *before* yq runs, so a failing yq left
#    an empty file that `mv` then moved over streams.yml. 253 bytes to 0. The
#    .orig backup only helps once, since a second run copies the wreckage over
#    it. Here nothing is written to streams.yml until yq has exited 0 AND
#    produced a non-empty file that still parses.
#
#  - `.thumb = $ID` overwrote hand-picked thumbs on every run. `//=` assigns
#    only when the key is absent or null, so curation survives. Use --force to
#    deliberately re-take them.
#
#  - a stray assets/streams/foo.json for a set not in streams.yml made jq
#    CREATE `sets.foo` holding nothing but a thumb -- no base, no ext. Only
#    sets already present are touched now.
#
#  - an empty id list made `.[0]` return null, which was written as the literal
#    string 'null'. Those are skipped.
#
# Note: python-yq round-trips through JSON, so COMMENTS IN streams.yml ARE
# LOST. If that matters, see the ruamel.yaml note at the bottom of this file.

set -euo pipefail

DATAFILE="${DATAFILE:-_data/streams.yml}"
STREAMDIR="${STREAMDIR:-assets/streams}"
FORCE="${1:-}"

[ -f "$DATAFILE" ] || { echo "no $DATAFILE" >&2; exit 1; }

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

# Collect set -> first id as one JSON object, so streams.yml is rewritten once
# instead of once per set.
MAP="$(
  for f in "$STREAMDIR"/*.json; do
    [ -e "$f" ] || continue
    s="$(basename "$f" .json)"
    id="$(jq -r '.[0] // empty' "$f" 2>/dev/null || true)"
    if [ -z "$id" ]; then
      echo "skip   $s (no ids)" >&2
      continue
    fi
    jq -n --arg s "$s" --arg i "$id" '{($s): $i}'
  done | jq -s 'add // {}'
)"

if [ "$(jq 'length' <<<"$MAP")" -eq 0 ]; then
  echo "nothing to do" >&2
  exit 0
fi

# with_entries walks only the sets that already exist, so a stray json file
# cannot invent one. //= leaves an existing thumb alone; = takes it over.
if [ "$FORCE" = "--force" ]; then
  ASSIGN='.value.thumb = $M[.key]'
else
  ASSIGN='.value.thumb //= $M[.key]'
fi

yq -y --argjson M "$MAP" "
  .sets |= with_entries(if \$M[.key] then $ASSIGN else . end)
" "$DATAFILE" > "$TMP"

# Guards before anything touches the real file: yq can exit 0 and still write
# nothing, and a truncated write would still be valid-looking on disk.
[ -s "$TMP" ] || { echo "yq produced an empty file -- $DATAFILE untouched" >&2; exit 1; }
yq -e '.sets | length > 0' "$TMP" >/dev/null \
  || { echo "result has no sets -- $DATAFILE untouched" >&2; exit 1; }

cp "$TMP" "$DATAFILE"

jq -r 'to_entries[] | "set    \(.key)  \(.value)"' <<<"$MAP"
echo "wrote $DATAFILE"

# ---------------------------------------------------------------------------
# Preserving comments
#
# python-yq (the one with --arg) parses to JSON and re-emits, so comments and
# key order style do not survive. If streams.yml carries comments you want,
# either switch to mikefarah's yq, which edits YAML in place:
#
#     yq -i '.sets.venture-capital.thumb = "aaa-111"' _data/streams.yml
#
# or do it in Python with ruamel.yaml, whose round-trip loader keeps comments:
#
#     from ruamel.yaml import YAML
#     y = YAML(); y.preserve_quotes = True
#     d = y.load(open(path))
#     d["sets"][name].setdefault("thumb", first_id)
#     y.dump(d, open(path, "w"))
# ---------------------------------------------------------------------------
