import glob
import json
import os
import random
import sys

try:
    sets = json.load(sys.stdin) or {}
except json.JSONDecodeError:
    # yq already printed its parse error; do not bury it under a traceback
    print("could not read sets from the data file", file=sys.stderr)
    sys.exit(1)

streamdir = sys.argv[1]
per = int(sys.argv[2])
seed = sys.argv[3]
setdir = sys.argv[4]

# Same merge as _plugins/set_data.rb: the stream key is "set" inside each file.
for f in sorted(glob.glob(os.path.join(setdir, "*.json"))):
    cfg = json.load(open(f))
    key = cfg.pop("set", None)
    if not key:
        print(f"{f}: missing \"set\"", file=sys.stderr)
        sys.exit(1)
    if key in sets:
        print(f"{f}: set {key} is already defined", file=sys.stderr)
        sys.exit(1)
    sets[key] = cfg
rng = random.Random(seed) if seed else random.Random()

out, skipped = {}, []
for name, cfg in (sets or {}).items():
    path = os.path.join(streamdir, name + ".json")
    if not os.path.exists(path):
        skipped.append(f"{name} (no {path})")
        continue
    try:
        ids = json.load(open(path))
    except Exception as e:
        skipped.append(f"{name} (unreadable: {e})")
        continue
    ids = [i for i in ids if isinstance(i, str) and i]
    if not ids:
        skipped.append(f"{name} (no ids)")
        continue
    cfg = cfg or {}
    base = cfg.get("base")
    if not base:
        skipped.append(f"{name} (no base)")
        continue

    # Carry the whole set entry through, not just base/ext: the stream
    # component builds a source descriptor from these and reads largeBase and
    # meta off it. Copying everything means a new key added to streams.yml
    # reaches the modal without touching this script.
    entry = {k: v for k, v in cfg.items() if k != "ids"}
    entry["base"] = base
    entry["ext"] = cfg.get("ext", "png")
    # tolerate either spelling; the JS side reads largeBase
    entry["largeBase"] = cfg.get("largeBase") or cfg.get("large_base") or base
    entry["meta"] = cfg.get("meta", "")
    entry["ids"] = rng.sample(ids, min(per, len(ids)))
    out[name] = entry

if not out:
    print("no sets resolved", file=sys.stderr)
    sys.exit(1)

json.dump({"sets": out}, sys.stdout, separators=(",", ":"))
for s in skipped:
    print("skip   " + s, file=sys.stderr)

total = sum(len(v["ids"]) for v in out.values())
print(f"pooled {total} ids from {len(out)} sets", file=sys.stderr)
