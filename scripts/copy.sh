#!/usr/bin/env bash
# Upload results/run-XX/*.json to a per-run S3 prefix.
#
# Usage:
#   ./upload_results.sh            # upload
#   DRYRUN=1 ./upload_results.sh   # show what would be uploaded
#
# Runs not listed in PREFIX are skipped with a warning.
 
set -euo pipefail

SOURCE=(
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-12-computing/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-12-pearl-earring/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-12-memento-mori/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-dumpster-fire/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-news-profile/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-lake-water/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-modern-painting/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-old-computers/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-obsolete-masters/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-masks/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-27-dress-code/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-30-sci-fi/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-30-framed/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-30-icee/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-30-grocery-shopping/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-30-icee/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-09-30-sci-fi/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-01-black-holes/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-02-burnt-sockets/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-02-tombstone/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-02-drip-pope/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-02-desert-rocks/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-02-health-food/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-03-invisible-tanks/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-05-modern-painting/"
  "s3://dac2ef3da2-exercises-or-excuses-site-content-use1/assets/img/2026-10-05-cloud-outline/"
)

SOURCE_BUCKET="dac2ef3da2-exercises-or-excuses-site-content-use1"
DEST_BUCKET="theunending-ai-site-content-use1"
for S in "${SOURCE[@]}"; do 
  D=$( echo "s3://${DEST_BUCKET}${S#s3://$SOURCE_BUCKET}" )
  echo "${S} -> ${D}"
  aws s3 sync "${S}" "${D}"
done

