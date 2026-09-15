from datetime import datetime, timezone
from pathlib import Path

from scripts.backup_media import create_media_backup
from scripts.check_media_backup_health import build_media_backup_health_report


def create_backup(tmp_path, timestamp):
    source = tmp_path / "uploads"
    source.mkdir(exist_ok=True)
    (source / "photo.jpg").write_bytes(b"image" * 500)
    return create_media_backup(
        source,
        tmp_path / "backups",
        now=datetime.strptime(timestamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc),
    )


def test_media_backup_health_accepts_fresh_verified_archive(tmp_path):
    create_backup(tmp_path, "20260815_030000")

    report = build_media_backup_health_report(
        tmp_path / "backups",
        now=datetime(2026, 8, 15, 4, tzinfo=timezone.utc),
    )

    assert report["ready"] is True
    assert report["checksum_valid"] is True
    assert report["archive_verified"] is True
    assert report["files"] == 1


def test_media_backup_health_rejects_tampering_and_staleness(tmp_path):
    backup = create_backup(tmp_path, "20260101_000000")
    Path(backup["archive"]).write_bytes(b"tampered")

    report = build_media_backup_health_report(
        tmp_path / "backups",
        max_age_hours=24,
        now=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    assert report["ready"] is False
    assert report["checksum_valid"] is False
    assert "Latest media backup is stale." in report["blockers"]


def test_media_backup_health_rejects_missing_archive(tmp_path):
    report = build_media_backup_health_report(tmp_path)

    assert report["ready"] is False
    assert report["latest_archive"] is None
