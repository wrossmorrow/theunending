#!/usr/bin/env bash
#
# Upload _site to the site bucket WITHOUT listing the whole bucket.
#
# `aws s3 sync _site/ s3://bucket/` lists every object under the destination
# before comparing -- here that is ~half a million set images and their JSON,
# which is what made deploys crawl. --exclude doesn't help: the CLI lists
# first and filters after.
#
# So sync is only ever pointed at prefixes the build owns:
#   - files at a level        -> `aws s3 cp --recursive --exclude "*/*"`
#                                (cp never lists the destination)
#   - subdirectories          -> `aws s3 sync` each one separately
#   - levels in DESCEND        -> walked into instead of synced whole, because
#                                the bucket holds bulk content beside them
#                                (assets/img/<set>/ lives next to the site's
#                                own assets/img/about/, posters/, ...)
#
# Nothing is ever deleted: no --delete. Workflows write straight to the
# bucket, so a stale object is cheaper than a destroyed one.
#
#   BUCKET=... [DIST=...] scripts/deploy.sh [--dryrun]
#
# Extra args go to every aws s3 command. With --dryrun nothing is uploaded
# and the CloudFront invalidation is skipped.

set -euo pipefail
shopt -s nullglob

BUCKET="${BUCKET:?set BUCKET}"
DIST="${DIST:-}"
SITE="${SITE:-_site}"
EXTRA=("$@")
# ${EXTRA[@]+"${EXTRA[@]}"} below, not "${EXTRA[@]}": macOS bash 3.2 calls an
# empty array unbound under set -u.

# Prefixes walked level by level rather than synced whole. "" is the root.
DESCEND=("" "assets" "assets/img")

[ -d "$SITE" ] || { echo "no $SITE -- build first" >&2; exit 1; }

is_descend() { local x; for x in "${DESCEND[@]}"; do [ "$x" = "$1" ] && return 0; done; return 1; }

level() {
  local rel="$1" src dst d sub
  src="$SITE/${rel:+$rel/}"
  dst="s3://$BUCKET/${rel:+$rel/}"

  echo "files $dst"
  aws s3 cp "$src" "$dst" --recursive --exclude "*/*" --no-progress ${EXTRA[@]+"${EXTRA[@]}"}

  for d in "$src"*/; do
    sub="${d%/}"; sub="${sub#"$SITE/"}"
    if is_descend "$sub"; then
      level "$sub"
    else
      echo "sync  s3://$BUCKET/$sub/"
      aws s3 sync "$SITE/$sub" "s3://$BUCKET/$sub" --no-progress ${EXTRA[@]+"${EXTRA[@]}"}
    fi
  done
}

level ""

case " ${EXTRA[*]-} " in
  *" --dryrun "*) echo "dryrun: skipping invalidation" ;;
  *)
    if [ -n "$DIST" ]; then
      aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" --query 'Invalidation.Id' --output text
    fi
    ;;
esac
