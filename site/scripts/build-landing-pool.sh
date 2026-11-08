#!/usr/bin/env bash
#
# Build assets/landing-pool.json: a small random sample of image ids from
# every set, with each set's base URL and extension attached.
#
# Why a build artifact rather than Liquid: the id lists live in
# assets/streams/, and site.data only reads _data/, so Liquid cannot see them.
# Fetching every manifest at runtime would be one request of several hundred
# KB per set for a page that shows maybe sixty images. One small file, built
# once, costs one request.
#
# The work is in build_landing_pool.py (standard library only, so CI needs
# nothing extra). Env vars kept for compatibility: SETDIR DATAFILE STREAMDIR
# OUT PER_SET SEED.

set -euo pipefail
cd "$(dirname "$0")/.."

exec python3 scripts/build_landing_pool.py \
  --setdir "${SETDIR:-_data/set_streams}" \
  --datafile "${DATAFILE:-_data/streams.yml}" \
  --streamdir "${STREAMDIR:-assets/streams}" \
  --out "${OUT:-assets/landing-pool.json}" \
  --per-set "${PER_SET:-40}" \
  ${SEED:+--seed "$SEED"}
