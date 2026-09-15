import json
from datetime import datetime, timezone

from scripts.backup_postgres import file_sha256
from scripts.check_postgres_backup_health import build_backup_health_report


def create_verified_backup(directory, timestamp="20260815_030000"):
    archive = directory / f"novix_{timestamp}.dump"
    archive.write_bytes(b"verified-backup" * 100)
    checksum = file_sha256(archive)
    archive.with_suffix(".dump.sha256").write_text(f"{checksum}  {archive.name}\n")
    archive.with_suffix(".dump.json").write_text(json.dumps({
        "archive": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": checksum,
        "restore_verified": True,
    }))
    (directory / "backup-jobs.jsonl").write_text(json.dumps({
        "ok": True,
        "archive": archive.name,
        "sha256": checksum,
        "restore_verified": True,
    }) + "\n")
    return archive


def test_backup_health_accepts_fresh_verified_archive(tmp_path):
    create_verified_backup(tmp_path)

    report = build_backup_health_report(
        tmp_path,
        now=datetime(2026, 8, 15, 4, tzinfo=timezone.utc),
    )

    assert report["ready"] is True
    assert report["checksum_valid"] is True
    assert report["restore_verified"] is True
    assert report["audit_matches"] is True
    assert report["blockers"] == []


def test_backup_health_rejects_tampered_archive(tmp_path):
    archive = create_verified_backup(tmp_path)
    archive.write_bytes(b"tampered" * 200)

    report = build_backup_health_report(
        tmp_path,
        now=datetime(2026, 8, 15, 4, tzinfo=timezone.utc),
    )

    assert report["ready"] is False
    assert report["checksum_valid"] is False
    assert len(report["blockers"]) == 3


def test_backup_health_rejects_stale_or_missing_backup(tmp_path):
    missing = build_backup_health_report(tmp_path, now=datetime(2026, 8, 15, tzinfo=timezone.utc))
    assert missing["ready"] is False
    assert missing["latest_archive"] is None

    create_verified_backup(tmp_path, "20260101_000000")
    stale = build_backup_health_report(
        tmp_path,
        max_age_hours=24,
        now=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )
    assert stale["ready"] is False
    assert "Latest PostgreSQL backup is stale." in stale["blockers"]


def test_backup_health_validates_encrypted_export_when_audited(tmp_path):
    archive = create_verified_backup(tmp_path)
    encrypted = tmp_path / f"{archive.name}.enc"
    encrypted.write_bytes(b"encrypted-export" * 100)
    encrypted_checksum = file_sha256(encrypted)
    (tmp_path / f"{encrypted.name}.sha256").write_text(
        f"{encrypted_checksum}  {encrypted.name}\n"
    )
    audit = json.loads((tmp_path / "backup-jobs.jsonl").read_text())
    audit.update({
        "encrypted_archive": encrypted.name,
        "encrypted_sha256": encrypted_checksum,
    })
    (tmp_path / "backup-jobs.jsonl").write_text(json.dumps(audit) + "\n")

    report = build_backup_health_report(
        tmp_path,
        now=datetime(2026, 8, 15, 4, tzinfo=timezone.utc),
    )

    assert report["ready"] is True
    assert report["encrypted_export_present"] is True
    assert report["encrypted_export_valid"] is True
