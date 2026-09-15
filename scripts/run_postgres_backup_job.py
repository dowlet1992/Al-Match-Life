#!/usr/bin/env python3
"""Run one serialized PostgreSQL backup job and append a PII-free audit record."""

import argparse
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_postgres import create_backup, file_sha256
from scripts.postgres_backup_crypto import encrypt_archive


class JobAlreadyRunning(RuntimeError):
    pass


@contextmanager
def exclusive_job_lock(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as lock_file:
        path.chmod(0o600)
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise JobAlreadyRunning("A PostgreSQL backup job is already running") from exc
        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def append_audit_record(path, record):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as destination:
        destination.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    path.chmod(0o600)


def run_backup_job(
    *,
    container,
    database,
    user,
    output_dir,
    verify=True,
    keep_count=14,
    keep_days=30,
    backup_creator=create_backup,
    backup_encryptor=encrypt_archive,
    encrypt_for_offsite=False,
    now=None,
):
    started_at = now or datetime.now(timezone.utc)
    output_dir = Path(output_dir).resolve()
    lock_path = output_dir / ".backup.lock"
    audit_path = output_dir / "backup-jobs.jsonl"
    try:
        with exclusive_job_lock(lock_path):
            report = backup_creator(
                container,
                database,
                user,
                output_dir,
                verify=verify,
                keep_count=keep_count,
                keep_days=keep_days,
            )
            if encrypt_for_offsite:
                encrypted_path = backup_encryptor(report["archive"])
                encrypted_checksum = file_sha256(encrypted_path)
                encrypted_checksum_path = Path(f"{encrypted_path}.sha256")
                encrypted_checksum_path.write_text(
                    f"{encrypted_checksum}  {encrypted_path.name}\n",
                    encoding="utf-8",
                )
                encrypted_checksum_path.chmod(0o600)
                report.update({
                    "encrypted_archive": str(encrypted_path),
                    "encrypted_bytes": encrypted_path.stat().st_size,
                    "encrypted_sha256": encrypted_checksum,
                    "encrypted_checksum_file": str(encrypted_checksum_path),
                })
        audit = {
            "at": started_at.isoformat(),
            "ok": True,
            "archive": Path(report["archive"]).name,
            "bytes": report["bytes"],
            "sha256": report["sha256"],
            "restore_verified": report["verified"],
            "retention_removed_count": len(report["retention_removed"]),
        }
        if report.get("encrypted_archive"):
            audit.update({
                "encrypted_archive": Path(report["encrypted_archive"]).name,
                "encrypted_bytes": report["encrypted_bytes"],
                "encrypted_sha256": report["encrypted_sha256"],
            })
        append_audit_record(audit_path, audit)
        return {**report, "audit_log": str(audit_path)}
    except Exception as exc:
        append_audit_record(audit_path, {
            "at": started_at.isoformat(),
            "ok": False,
            "error_type": type(exc).__name__,
        })
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the serialized NOVIX PostgreSQL backup job.")
    parser.add_argument("--container", default="novix-postgres-staging")
    parser.add_argument("--database", default="novix")
    parser.add_argument("--user", default="novix")
    parser.add_argument("--output-dir", default="backups/postgres")
    parser.add_argument("--keep-count", type=int, default=14)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--encrypt-for-offsite", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_backup_job(
            container=args.container,
            database=args.database,
            user=args.user,
            output_dir=args.output_dir,
            verify=not args.no_verify,
            keep_count=args.keep_count,
            keep_days=args.keep_days,
            encrypt_for_offsite=args.encrypt_for_offsite,
        )
    except JobAlreadyRunning:
        print(json.dumps({"ok": False, "error": "backup_already_running"}))
        return 75
    except Exception:
        print(json.dumps({"ok": False, "error": "backup_failed"}))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
