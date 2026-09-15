# NOVIX PostgreSQL backup runbook

## Create and verify a backup

Run from the project root while the PostgreSQL container is available:

```bash
python3 scripts/backup_postgres.py --verify --pretty
```

The command creates three private (`0600`) files in `backups/postgres/`:

- `novix_<UTC timestamp>.dump` — PostgreSQL custom-format archive;
- `novix_<UTC timestamp>.dump.sha256` — integrity checksum;
- `novix_<UTC timestamp>.dump.json` — machine-readable verification manifest.

Verification restores the archive into a temporary, timestamped database, checks
the public table and core record counts, and removes that database even when a
verification step fails. The live database is never used as a restore target.

## Retention

Defaults retain at least the newest 14 archives and every archive newer than 30
days. An archive is deleted only when it is outside both protections. Cleanup
recognizes only the strict NOVIX timestamp filename and removes its checksum and
manifest together; unrelated files are ignored.

Customize the policy when required:

```bash
python3 scripts/backup_postgres.py --verify --keep-count 30 --keep-days 90
```

## Scheduling

For database-only maintenance use the serialized PostgreSQL wrapper:

```bash
python3 scripts/run_postgres_backup_job.py --pretty
```

It prevents overlapping jobs and appends a PII-free audit event to the private
`backup-jobs.jsonl` file. Exit code `75` means another backup is already running;
exit code `1` means the backup failed.

Check backup freshness, checksum, restore evidence, and the audit chain with:

```bash
python3 scripts/check_postgres_backup_health.py --pretty
```

The check exits with `0` only when the newest archive is no older than 26 hours,
its checksum is valid, its restore manifest is valid, and it matches the latest
successful job audit record. It exits with `1` and reports PII-free blockers for
monitoring systems otherwise.

The same backup health result is a mandatory part of `scripts/release_gate.py`;
a stale, damaged, or unverified archive blocks deployment.

The normal unattended task is the combined database and media backup set:

```bash
python3 scripts/run_full_backup_job.py --pretty
```

The repository includes its macOS launchd template at
`ops/launchd/com.novix.full-backup.plist.example`. It runs daily at 03:00 local
time with database restore and media archive verification enabled. Recheck its
absolute Python and project paths before installing it. Production Linux or
container deployments should invoke the same wrapper from a systemd timer or
Kubernetes CronJob.

Alert on a non-zero exit code and copy the resulting three files to encrypted
off-site storage. Do not place encryption keys in this repository.

## Integrity and restore drill

Verify a copied archive before retaining it off-site:

```bash
cd backups/postgres
shasum -a 256 -c novix_<timestamp>.dump.sha256
```

Run `--verify` on every backup and perform a documented restore drill against a
disposable environment before each production release. Never restore a drill
directly over the live NOVIX database.

## Encryption for off-site storage

PostgreSQL archives contain sensitive user data. Before copying an archive to an
external destination, encrypt it with the dedicated backup key:

```bash
export NOVIX_BACKUP_ENCRYPTION_KEY="$(openssl rand -base64 32)"
python3 scripts/postgres_backup_crypto.py encrypt backups/postgres/novix_<timestamp>.dump
```

Generate the key once, move it immediately into the production secret manager,
and reuse that managed key for scheduled encryption and disaster recovery. Do
not generate a new untracked key for every backup.

For the complete unattended backup set, enable encryption in the same locked operation:

```bash
python3 scripts/run_full_backup_job.py --encrypt-for-offsite --pretty
```

This creates `<archive>.enc.sha256`, records the encrypted artifact in the
private audit chain, and makes the health check validate its integrity.

Store that key in the production secret manager, never in `.env`, Git, the
archive directory, or the same storage account as the encrypted archive. The
streaming `NOVIXBK1` format uses AES-256-GCM and private `0600` output files.

For a restore drill, decrypt to a new disposable path:

```bash
python3 scripts/postgres_backup_crypto.py decrypt \
  backups/postgres/novix_<timestamp>.dump.enc \
  --output /private/tmp/novix-restore.dump
```

An incorrect key or modified ciphertext fails authentication and leaves no
partial plaintext file behind.
