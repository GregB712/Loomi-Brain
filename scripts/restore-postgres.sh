#!/usr/bin/env bash
set -euo pipefail

: "${BACKUP_FILE:?Set BACKUP_FILE to a PostgreSQL custom-format dump.}"

if [[ "${CONFIRM_RESTORE:-}" != "RESTORE_DEV_DATA" ]]; then
  printf 'Refusing restore. Set CONFIRM_RESTORE=RESTORE_DEV_DATA for local/dev restore.\n' >&2
  exit 2
fi

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/compose.yml}"
POSTGRES_DB="${LOOMI_POSTGRES_DB:-loomi_brain}"
POSTGRES_USER="${LOOMI_POSTGRES_USER:-loomi}"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" <"${BACKUP_FILE}"

printf 'PostgreSQL restore completed from: %s\n' "${BACKUP_FILE}"
