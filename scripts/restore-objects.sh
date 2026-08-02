#!/usr/bin/env bash
set -euo pipefail

: "${OBJECT_BACKUP_FILE:?Set OBJECT_BACKUP_FILE to an object tar.gz archive.}"

if [[ "${CONFIRM_RESTORE:-}" != "RESTORE_DEV_DATA" ]]; then
  printf 'Refusing object restore. Set CONFIRM_RESTORE=RESTORE_DEV_DATA for local/dev restore.\n' >&2
  exit 2
fi

OBJECT_VOLUME="${LOOMI_OBJECT_VOLUME:-docker_loomi-api-objects}"
OBJECT_BACKUP_ABS="$(realpath "${OBJECT_BACKUP_FILE}")"
OBJECT_BACKUP_DIR="$(dirname "${OBJECT_BACKUP_ABS}")"
OBJECT_BACKUP_NAME="$(basename "${OBJECT_BACKUP_ABS}")"

docker run --rm \
  --volume "${OBJECT_VOLUME}:/data" \
  --volume "${OBJECT_BACKUP_DIR}:/backup:ro" \
  busybox:1.37 \
  sh -c 'find /data -mindepth 1 -maxdepth 1 -exec rm -rf {} + && tar -xzf "/backup/$1" -C /data' \
  sh "${OBJECT_BACKUP_NAME}"

printf 'Object restore completed from: %s\n' "${OBJECT_BACKUP_FILE}"
