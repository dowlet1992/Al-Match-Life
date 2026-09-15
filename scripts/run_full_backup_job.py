#!/usr/bin/env python3
"""Create one verified PostgreSQL + media backup set under a shared lock."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_media import create_media_backup
from scripts.backup_postgres import create_backup, file_sha256
from scripts.postgres_backup_crypto import encrypt_archive
from scripts.run_postgres_backup_job import JobAlreadyRunning, append_audit_record, exclusive_job_lock


def encrypted_export(path, encryptor=encrypt_archive):
    encrypted = encryptor(path)
    checksum = file_sha256(encrypted)
    checksum_path = Path(f"{encrypted}.sha256")
    checksum_path.write_text(f"{checksum}  {encrypted.name}\n", encoding="utf-8")
    checksum_path.chmod(0o600)
    return {
        "archive": str(encrypted),
        "bytes": encrypted.stat().st_size,
        "sha256": checksum,
        "checksum_file": str(checksum_path),
    }


def run_full_backup_job(
    *,
    container,
    database,
    user,
    media_source,
    backup_root,
    keep_count=14,
    keep_days=30,
    encrypt_for_offsite=False,
    postgres_creator=create_backup,
    media_creator=create_media_backup,
    encryptor=encrypt_archive,
    now=None,
):
    started_at = now or datetime.now(timezone.utc)
    backup_root = Path(backup_root).resolve()
    postgres_dir = backup_root / "postgres"
    media_dir = backup_root / "media"
    sets_dir = backup_root / "sets"
    audit_path = backup_root / "backup-set-jobs.jsonl"
    lock_path = backup_root / ".full-backup.lock"
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")
    set_id = f"novix_backup_set_{timestamp}"
    try:
        with exclusive_job_lock(lock_path):
            postgres = postgres_creator(
                container,
                database,
                user,
                postgres_dir,
                verify=True,
                now=started_at,
                keep_count=keep_count,
                keep_days=keep_days,
            )
            media = media_creator(
                media_source,
                media_dir,
                now=started_at,
                keep_count=keep_count,
                keep_days=keep_days,
            )
            encrypted = {}
            if encrypt_for_offsite:
                encrypted = {
                    "postgres": encrypted_export(postgres["archive"], encryptor),
                    "media": encrypted_export(media["archive"], encryptor),
                }
            sets_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = sets_dir / f"{set_id}.json"
            manifest = {
                "format_version": 1,
                "set_id": set_id,
                "created_at": started_at.isoformat(),
                "verified": bool(postgres["verified"] and media["verified"]),
                "postgres": {
                    "archive": Path(postgres["archive"]).name,
                    "bytes": postgres["bytes"],
                    "sha256": postgres["sha256"],
                    "restored_counts": postgres["restored_counts"],
                },
                "media": {
                    "archive": Path(media["archive"]).name,
                    "bytes": media["bytes"],
                    "sha256": media["sha256"],
                    "files": media["files"],
                    "uncompressed_bytes": media["uncompressed_bytes"],
                },
                "encrypted_exports": {
                    name: {
                        "archive": Path(report["archive"]).name,
                        "bytes": report["bytes"],
                        "sha256": report["sha256"],
                    }
                    for name, report in encrypted.items()
                },
            }
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            manifest_path.chmod(0o600)
            append_audit_record(postgres_dir / "backup-jobs.jsonl", {
                "at": started_at.isoformat(),
                "ok": True,
                "archive": Path(postgres["archive"]).name,
                "bytes": postgres["bytes"],
                "sha256": postgres["sha256"],
                "restore_verified": postgres["verified"],
                "retention_removed_count": len(postgres["retention_removed"]),
                **({
                    "encrypted_archive": Path(encrypted["postgres"]["archive"]).name,
                    "encrypted_bytes": encrypted["postgres"]["bytes"],
                    "encrypted_sha256": encrypted["postgres"]["sha256"],
                } if encrypted else {}),
            })
        append_audit_record(audit_path, {
            "at": started_at.isoformat(),
            "ok": True,
            "set_id": set_id,
            "postgres_sha256": postgres["sha256"],
            "media_sha256": media["sha256"],
            "media_files": media["files"],
            "encrypted": bool(encrypted),
        })
        return {
            "ok": True,
            "set_id": set_id,
            "manifest": str(manifest_path),
            "postgres": postgres,
            "media": media,
            "encrypted_exports": encrypted,
            "audit_log": str(audit_path),
        }
    except Exception as exc:
        append_audit_record(audit_path, {
            "at": started_at.isoformat(),
            "ok": False,
            "set_id": set_id,
            "error_type": type(exc).__name__,
        })
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create one verified NOVIX database and media backup set.")
    parser.add_argument("--container", default="novix-postgres-staging")
    parser.add_argument("--database", default="novix")
    parser.add_argument("--user", default="novix")
    parser.add_argument("--media-source", default="uploads")
    parser.add_argument("--backup-root", default="backups")
    parser.add_argument("--keep-count", type=int, default=14)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--encrypt-for-offsite", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_full_backup_job(
            container=args.container,
            database=args.database,
            user=args.user,
            media_source=args.media_source,
            backup_root=args.backup_root,
            keep_count=args.keep_count,
            keep_days=args.keep_days,
            encrypt_for_offsite=args.encrypt_for_offsite,
        )
    except JobAlreadyRunning:
        print(json.dumps({"ok": False, "error": "backup_already_running"}))
        return 75
    except Exception:
        print(json.dumps({"ok": False, "error": "backup_set_failed"}))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
