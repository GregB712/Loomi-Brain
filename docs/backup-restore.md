# Backup, Restore, Export, And Delete

Reader: operator running the local/private Loomi-Brain stack.

Post-read action: create, verify, and rehearse development backup artifacts without risking production data.

## PostgreSQL Backup

```bash
scripts/backup-postgres.sh
```

The script writes a custom-format dump and SHA-256 checksum under `backups/`.

## Object Backup

```bash
scripts/backup-objects.sh
```

The script archives the private object volume and writes a checksum.

Set `LOOMI_OBJECT_VOLUME` if your Compose project name changes the generated volume name.

## Verify Artifacts

```bash
BACKUP_FILE=backups/postgres/<dump-file> \
OBJECT_BACKUP_FILE=backups/objects/<tar-file> \
scripts/verify-restore-artifacts.sh
```

This checks PostgreSQL dump readability, object archive readability, and checksums when present.

## Restore To Development

Restores are destructive and require explicit confirmation:

```bash
CONFIRM_RESTORE=RESTORE_DEV_DATA \
BACKUP_FILE=backups/postgres/<dump-file> \
scripts/restore-postgres.sh

CONFIRM_RESTORE=RESTORE_DEV_DATA \
OBJECT_BACKUP_FILE=backups/objects/<tar-file> \
scripts/restore-objects.sh
```

Never point these scripts at a non-development database without rewriting the guardrails for that environment.

## Owner Data Export

```bash
scripts/export-owner-data.sh
```

The export combines database and private-object artifacts. Treat the output as sensitive owner data.

## Development Deletion

Deletion is local/test only and requires confirmation:

```bash
LOOMI_ENVIRONMENT=local \
CONFIRM_DELETE=DELETE_LOCAL_OWNER_DATA \
scripts/delete-owner-data-dev.sh
```

Re-seed the development owner after deletion:

```bash
make seed
```

## Disaster-Recovery Smoke Exercise

```bash
scripts/disaster-recovery-smoke.sh
```

The smoke exercise creates fresh backup artifacts and verifies they are readable. It does not restore over the active database.
