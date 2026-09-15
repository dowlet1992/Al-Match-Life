import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.run_postgres_backup_job import (
    JobAlreadyRunning,
    exclusive_job_lock,
    run_backup_job,
)


def test_backup_job_writes_private_pii_free_audit_record(tmp_path):
    def backup_creator(*args, **kwargs):
        return {
            "ok": True,
            "archive": str(tmp_path / "novix_20260815_030000.dump"),
            "bytes": 4096,
            "sha256": "a" * 64,
            "verified": True,
            "restored_counts": {"users": 8},
            "retention_removed": [],
        }

    report = run_backup_job(
        container="novix-postgres-staging",
        database="novix",
        user="novix",
        output_dir=tmp_path,
        backup_creator=backup_creator,
        now=datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc),
    )

    audit_path = Path(report["audit_log"])
    audit = json.loads(audit_path.read_text())
    assert audit["ok"] is True
    assert audit["archive"] == "novix_20260815_030000.dump"
    assert "users" not in audit
    assert audit_path.stat().st_mode & 0o777 == 0o600


def test_backup_job_records_only_failure_type(tmp_path):
    def failing_creator(*args, **kwargs):
        raise RuntimeError("secret database details")

    with pytest.raises(RuntimeError):
        run_backup_job(
            container="novix-postgres-staging",
            database="novix",
            user="novix",
            output_dir=tmp_path,
            backup_creator=failing_creator,
        )

    audit = json.loads((tmp_path / "backup-jobs.jsonl").read_text())
    assert audit["ok"] is False
    assert audit["error_type"] == "RuntimeError"
    assert "secret" not in json.dumps(audit)


def test_exclusive_backup_lock_rejects_second_owner(tmp_path):
    lock_path = tmp_path / ".backup.lock"
    with exclusive_job_lock(lock_path):
        with pytest.raises(JobAlreadyRunning):
            with exclusive_job_lock(lock_path):
                pass


def test_backup_job_creates_encrypted_offsite_export(tmp_path):
    archive = tmp_path / "novix_20260815_030000.dump"
    archive.write_bytes(b"database" * 200)

    def backup_creator(*args, **kwargs):
        return {
            "ok": True,
            "archive": str(archive),
            "bytes": archive.stat().st_size,
            "sha256": "a" * 64,
            "verified": True,
            "restored_counts": {},
            "retention_removed": [],
        }

    def backup_encryptor(source):
        encrypted = Path(f"{source}.enc")
        encrypted.write_bytes(b"encrypted" * 200)
        encrypted.chmod(0o600)
        return encrypted

    report = run_backup_job(
        container="novix-postgres-staging",
        database="novix",
        user="novix",
        output_dir=tmp_path,
        backup_creator=backup_creator,
        backup_encryptor=backup_encryptor,
        encrypt_for_offsite=True,
    )

    assert Path(report["encrypted_archive"]).exists()
    assert Path(report["encrypted_checksum_file"]).stat().st_mode & 0o777 == 0o600
    audit = json.loads((tmp_path / "backup-jobs.jsonl").read_text())
    assert audit["encrypted_archive"].endswith(".dump.enc")
    assert audit["encrypted_sha256"] == report["encrypted_sha256"]
