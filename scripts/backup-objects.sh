#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-backups/objects}"
OBJECT_VOLUME="${LOOMI_OBJECT_VOLUME:-docker_loomi-api-objects}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/loomi-objects-${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"
BACKUP_DIR_ABS="$(realpath "${BACKUP_DIR}")"

docker run --rm \
  --volume "${OBJECT_VOLUME}:/data:ro" \
  --volume "${BACKUP_DIR_ABS}:/backup" \
  busybox:1.37 \
  tar -czf "/backup/$(basename "${BACKUP_FILE}")" -C /data .

sha256sum "${BACKUP_FILE}" >"${BACKUP_FILE}.sha256"
printf 'Object backup written: %s\n' "${BACKUP_FILE}"
