#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-backups/postgres}"
POSTGRES_DB="${LOOMI_POSTGRES_DB:-loomi_brain}"
POSTGRES_USER="${LOOMI_POSTGRES_USER:-loomi}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/loomi-postgres-${STAMP}.dump"

mkdir -p "${BACKUP_DIR}"

docker compose -f "${COMPOSE_FILE}" exec -T postgres \
  pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" >"${BACKUP_FILE}"

sha256sum "${BACKUP_FILE}" >"${BACKUP_FILE}.sha256"
printf 'PostgreSQL backup written: %s\n' "${BACKUP_FILE}"
