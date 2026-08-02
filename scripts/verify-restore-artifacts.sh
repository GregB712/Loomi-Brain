#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BACKUP_FILE:-}" ]]; then
  if command -v pg_restore >/dev/null 2>&1; then
    pg_restore --list "${BACKUP_FILE}" >/dev/null
  else
    COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/compose.yml}"
    docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_restore --list <"${BACKUP_FILE}" >/dev/null
  fi
  if [[ -f "${BACKUP_FILE}.sha256" ]]; then
    sha256sum --check "${BACKUP_FILE}.sha256"
  fi
  printf 'Verified PostgreSQL backup artifact: %s\n' "${BACKUP_FILE}"
fi

if [[ -n "${OBJECT_BACKUP_FILE:-}" ]]; then
  tar -tzf "${OBJECT_BACKUP_FILE}" >/dev/null
  if [[ -f "${OBJECT_BACKUP_FILE}.sha256" ]]; then
    sha256sum --check "${OBJECT_BACKUP_FILE}.sha256"
  fi
  printf 'Verified object backup artifact: %s\n' "${OBJECT_BACKUP_FILE}"
fi

if [[ -z "${BACKUP_FILE:-}" && -z "${OBJECT_BACKUP_FILE:-}" ]]; then
  printf 'Set BACKUP_FILE, OBJECT_BACKUP_FILE, or both.\n' >&2
  exit 2
fi
