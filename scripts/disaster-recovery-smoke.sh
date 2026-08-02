#!/usr/bin/env bash
set -euo pipefail

DR_DIR="${DR_DIR:-backups/dr-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "${DR_DIR}"

postgres_output="$(BACKUP_DIR="${DR_DIR}/postgres" scripts/backup-postgres.sh)"
objects_output="$(BACKUP_DIR="${DR_DIR}/objects" scripts/backup-objects.sh)"

postgres_file="$(printf '%s\n' "${postgres_output}" | awk -F': ' '/PostgreSQL backup written/ {print $2}')"
objects_file="$(printf '%s\n' "${objects_output}" | awk -F': ' '/Object backup written/ {print $2}')"

BACKUP_FILE="${postgres_file}" OBJECT_BACKUP_FILE="${objects_file}" scripts/verify-restore-artifacts.sh

cat >"${DR_DIR}/README.txt" <<DR
Synthetic disaster-recovery smoke exercise
created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
postgres_backup=${postgres_file}
object_backup=${objects_file}

This exercise verifies backup creation and artifact readability. It does not restore
over the active database. For a full local restore rehearsal, use:

CONFIRM_RESTORE=RESTORE_DEV_DATA BACKUP_FILE=${postgres_file} scripts/restore-postgres.sh
CONFIRM_RESTORE=RESTORE_DEV_DATA OBJECT_BACKUP_FILE=${objects_file} scripts/restore-objects.sh
DR

printf 'Disaster-recovery smoke exercise written: %s\n' "${DR_DIR}"
