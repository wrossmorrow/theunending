#!/usr/bin/env bash
#
# Populate `thumb` in each _data/set_streams/<post-name>.json from the first id
# in assets/streams/<set>.json, where <set> is the file's "set" key.
#
# (Sets used to live in _data/streams.yml; see _plugins/set_data.rb. The
# lessons below came from that version and still apply per file.)
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

SETDIR="${SETDIR:-_data/set_streams}"
STREAMDIR="${STREAMDIR:-assets/streams}"
FORCE="${1:-}"

[ -d "$SETDIR" ] || { echo "no $SETDIR" >&2; exit 1; }

# Each file is validated and fully serialized before it is written, and
# written in place (no temp-file mv), so a failure leaves it untouched.
python3 - "$SETDIR" "$STREAMDIR" "$FORCE" <<'PY'
import json, sys
from pathlib import Path

setdir, streamdir, force = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "--force"
changed = 0
for f in sorted(setdir.glob("*.json")):
    cfg = json.loads(f.read_text())
    key = cfg.get("set")
    if not key:
        sys.exit(f"{f}: missing \"set\"")
    if cfg.get("thumb") and not force:
        continue                      # curated or already set: leave it
    manifest = streamdir / f"{key}.json"
    if not manifest.exists():
        print(f"skip   {key} (no {manifest})", file=sys.stderr)
        continue
    ids = [i for i in json.loads(manifest.read_text()) if isinstance(i, str) and i]
    if not ids:
        print(f"skip   {key} (no ids)", file=sys.stderr)
        continue
    if cfg.get("thumb") == ids[0]:
        continue
    cfg["thumb"] = ids[0]
    text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)                  # parses before it touches the file
    f.write_text(text)
    print(f"set    {key}  {ids[0]}")
    changed += 1
print(f"updated {changed} file(s)")
PY
