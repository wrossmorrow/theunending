# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml"]
# ///
"""
One-time backfill: split _data/streams.yml `sets` and _data/unending-posters.json
into one file per set, which _plugins/set_data.rb merges back at build time.

    _data/set_streams/<post-name>.json   {"set": <key>, base, manifest, meta, thumb}
    _data/set_posters/<post-name>.json   {size: {...}, ...}

<post-name> comes from the set's base URL (.../assets/img/<post-name>/), which
matches the post filename for every set. The stream key goes inside the file
because it can differ from the post name.

Writes nothing over an existing file, checks that merging the new files back
reproduces the originals exactly, and only then trims streams.yml to its
defaults and empties unending-posters.json.

    python3 scripts/split-set-data.py            # dry run: report only
    python3 scripts/split-set-data.py --write
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

BASE_RE = re.compile(r"/assets/img/(\d{4}-\d\d-\d\d-[^/]+)/?$")


def dump(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("_data"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    streams_path = args.data / "streams.yml"
    posters_path = args.data / "unending-posters.json"
    streams_dir = args.data / "set_streams"
    posters_dir = args.data / "set_posters"

    streams_text = streams_path.read_text()
    streams = yaml.safe_load(streams_text) or {}
    sets = streams.get("sets") or {}
    posters = json.loads(posters_path.read_text())

    out: dict[Path, object] = {}
    problems: list[str] = []

    for key, cfg in sets.items():
        m = BASE_RE.search((cfg or {}).get("base", ""))
        if not m:
            problems.append(f"set {key}: cannot derive a post name from base {cfg.get('base')!r}")
            continue
        out[streams_dir / f"{m.group(1)}.json"] = {"set": key, **cfg}

    for name, sizes in posters.items():
        out[posters_dir / f"{name}.json"] = sizes

    for path in out:
        if path.exists():
            problems.append(f"{path} already exists")

    # Round trip: merge the new files exactly as the plugin would and compare.
    merged_sets, merged_posters = {}, {}
    for path, obj in out.items():
        if path.parent == streams_dir:
            k = obj["set"]
            if k in merged_sets:
                problems.append(f"duplicate set key {k}")
            merged_sets[k] = {kk: vv for kk, vv in obj.items() if kk != "set"}
        else:
            merged_posters[path.stem] = obj
    if merged_sets != sets:
        problems.append("set round trip mismatch")
    if merged_posters != posters:
        problems.append("posters round trip mismatch")

    # streams.yml keeps everything before `sets:` verbatim (comments included).
    m = re.search(r"^sets:\s*$", streams_text, re.M)
    if not m:
        problems.append("no top-level `sets:` line in streams.yml")
    else:
        trimmed = streams_text[: m.start()].rstrip() + "\n"
        rest = yaml.safe_load(trimmed) or {}
        if rest != {k: v for k, v in streams.items() if k != "sets"}:
            problems.append("streams.yml has keys after `sets:`; trim by hand")

    n_streams = sum(1 for p in out if p.parent == streams_dir)
    n_posters = len(out) - n_streams
    print(f"{n_streams} set_streams files, {n_posters} set_posters files")
    if problems:
        for p in problems:
            print("error  " + p, file=sys.stderr)
        return 1
    if not args.write:
        print("dry run; pass --write")
        return 0

    streams_dir.mkdir(exist_ok=True)
    posters_dir.mkdir(exist_ok=True)
    for path, obj in out.items():
        with path.open("x") as f:  # "x": never overwrite
            f.write(dump(obj))
    streams_path.write_text(trimmed)
    posters_path.write_text("{}\n")
    print(f"wrote {len(out)} files; trimmed {streams_path} to defaults; emptied {posters_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
