#!/usr/bin/env bash
set -euo pipefail

EXPORT_DIR="${EXPORT_DIR:-exports/owner-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${EXPORT_DIR}"

BACKUP_DIR="${EXPORT_DIR}/postgres" scripts/backup-postgres.sh
BACKUP_DIR="${EXPORT_DIR}/objects" scripts/backup-objects.sh

cat >"${EXPORT_DIR}/manifest.txt" <<MANIFEST
Loomi-Brain owner data export
created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
environment=${LOOMI_ENVIRONMENT:-local}
postgres_dir=${EXPORT_DIR}/postgres
objects_dir=${EXPORT_DIR}/objects

This export contains the development database dump and private object-store archive.
Store it as sensitive owner data.
MANIFEST

printf 'Owner data export written: %s\n' "${EXPORT_DIR}"
