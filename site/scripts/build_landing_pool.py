"""
Build assets/landing-pool.json: a small random sample of image ids from every
set, with each set's stream config attached. Standard library only, so it runs
on a bare CI runner (no yq, no PyYAML).

Sets come from _data/set_streams/*.json, merged exactly as _plugins/set_data.rb
merges them (the stream key is "set" inside each file). _data/streams.yml only
holds `defaults` now; if a `sets:` block ever reappears there this fails loudly
rather than silently ignoring those sets.

    python3 scripts/build_landing_pool.py [--per-set 40] [--seed S] [--out PATH]

Nothing is written to --out until the whole result has been built and parses.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path


def load_sets(setdir: Path, datafile: Path) -> dict[str, dict]:
    if datafile.exists() and re.search(r"^sets\s*:", datafile.read_text(), re.M):
        sys.exit(f"{datafile} has a `sets:` block; move those sets into {setdir}/")
    sets: dict[str, dict] = {}
    for f in sorted(setdir.glob("*.json")):
        cfg = json.loads(f.read_text())
        key = cfg.pop("set", None)
        if not key:
            sys.exit(f'{f}: missing "set"')
        if key in sets:
            sys.exit(f"{f}: set {key} is already defined")
        sets[key] = cfg
    return sets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setdir", type=Path, default=Path("_data/set_streams"))
    ap.add_argument("--datafile", type=Path, default=Path("_data/streams.yml"))
    ap.add_argument("--streamdir", type=Path, default=Path("assets/streams"))
    ap.add_argument("--out", type=Path, default=Path("assets/landing-pool.json"))
    ap.add_argument("--per-set", type=int, default=40, help="ids sampled per set")
    ap.add_argument("--seed", default="", help="set for a reproducible pool")
    args = ap.parse_args()

    sets = load_sets(args.setdir, args.datafile)
    rng = random.Random(args.seed) if args.seed else random.Random()

    out, skipped = {}, []
    for name, cfg in sets.items():
        path = args.streamdir / f"{name}.json"
        if not path.exists():
            skipped.append(f"{name} (no {path})")
            continue
        try:
            ids = json.loads(path.read_text())
        except Exception as e:
            skipped.append(f"{name} (unreadable: {e})")
            continue
        ids = [i for i in ids if isinstance(i, str) and i]
        if not ids:
            skipped.append(f"{name} (no ids)")
            continue
        base = cfg.get("base")
        if not base:
            skipped.append(f"{name} (no base)")
            continue

        # Carry the whole set entry through, not just base/ext: the stream
        # component builds a source descriptor from these and reads largeBase
        # and meta off it, so a new key in a set file reaches the modal
        # without touching this script.
        entry = {k: v for k, v in cfg.items() if k != "ids"}
        entry["base"] = base
        entry["ext"] = cfg.get("ext", "png")
        entry["largeBase"] = cfg.get("largeBase") or cfg.get("large_base") or base
        entry["meta"] = cfg.get("meta", "")
        entry["ids"] = rng.sample(ids, min(args.per_set, len(ids)))
        out[name] = entry

    for s in skipped:
        print("skip   " + s, file=sys.stderr)
    if not out:
        print(f"no sets resolved -- {args.out} untouched", file=sys.stderr)
        return 1

    text = json.dumps({"sets": out}, separators=(",", ":"))
    json.loads(text)  # parses before it touches the real file
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    total = sum(len(v["ids"]) for v in out.values())
    print(f"pooled {total} ids from {len(out)} sets; wrote {args.out} ({len(text)} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
