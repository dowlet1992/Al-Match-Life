import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_full_backup_job import run_full_backup_job


def test_full_backup_job_creates_one_verified_private_set(tmp_path):
    def postgres_creator(*args, **kwargs):
        archive = Path(args[3]) / "novix_20260815_030000.dump"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"database")
        return {
            "archive": str(archive), "bytes": 8, "sha256": "a" * 64,
            "verified": True, "restored_counts": {"users": 8}, "retention_removed": [],
        }

    def media_creator(*args, **kwargs):
        archive = Path(args[1]) / "novix_media_20260815_030000.tar.gz"
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"media")
        return {
            "archive": str(archive), "bytes": 5, "sha256": "b" * 64,
            "verified": True, "files": 3, "uncompressed_bytes": 100,
            "retention_removed": [],
        }

    report = run_full_backup_job(
        container="postgres", database="novix", user="novix",
        media_source=tmp_path / "uploads", backup_root=tmp_path / "backups",
        postgres_creator=postgres_creator, media_creator=media_creator,
        now=datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
    )

    manifest_path = Path(report["manifest"])
    manifest = json.loads(manifest_path.read_text())
    audit = json.loads(Path(report["audit_log"]).read_text())
    postgres_audit = json.loads((tmp_path / "backups" / "postgres" / "backup-jobs.jsonl").read_text())
    assert manifest["verified"] is True
    assert manifest["postgres"]["sha256"] == "a" * 64
    assert manifest["media"]["sha256"] == "b" * 64
    assert audit["set_id"] == manifest["set_id"]
    assert postgres_audit["archive"] == manifest["postgres"]["archive"]
    assert postgres_audit["restore_verified"] is True
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert Path(report["audit_log"]).stat().st_mode & 0o777 == 0o600


def test_full_backup_job_does_not_publish_set_when_media_fails(tmp_path):
    def postgres_creator(*args, **kwargs):
        return {
            "archive": str(tmp_path / "db.dump"), "bytes": 8, "sha256": "a" * 64,
            "verified": True, "restored_counts": {}, "retention_removed": [],
        }

    def media_creator(*args, **kwargs):
        raise RuntimeError("private media failure detail")

    try:
        run_full_backup_job(
            container="postgres", database="novix", user="novix",
            media_source=tmp_path / "uploads", backup_root=tmp_path / "backups",
            postgres_creator=postgres_creator, media_creator=media_creator,
            now=datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
        )
    except RuntimeError:
        pass

    sets_dir = tmp_path / "backups" / "sets"
    assert not sets_dir.exists() or not list(sets_dir.glob("*.json"))
    audit = json.loads((tmp_path / "backups" / "backup-set-jobs.jsonl").read_text())
    assert audit["ok"] is False
    assert audit["error_type"] == "RuntimeError"
    assert "private" not in json.dumps(audit)
