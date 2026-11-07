#!/usr/bin/env bash
# /usr/local/bin/pg-backup.sh

set -euo pipefail

: ${BACKUP_BUCKET_NAME:?}

BACKUP_BUCKET_PREFIX="${BACKUP_BUCKET_PATH:-backups}"

cd /home/ubuntu/deploy
TS=$( date -u +%Y%m%dT%H%M%SZ )
docker compose exec -T postgres sh -c 'pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc' \
  | aws s3 cp - "s3://${BACKUP_BUCKET_NAME}/${BACKUP_BUCKET_PREFIX}/${POSTGRES_DB}/${TS}.dump"
