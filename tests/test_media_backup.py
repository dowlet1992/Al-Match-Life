import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.backup_media import create_media_backup, prune_media_backups, verify_media_archive


def test_media_backup_is_verified_private_and_preserves_relative_names(tmp_path):
    source = tmp_path / "uploads"
    (source / "users" / "abc").mkdir(parents=True)
    (source / "users" / "abc" / "photo.jpg").write_bytes(b"image" * 500)
    (source / "voice.webm").write_bytes(b"voice" * 400)

    report = create_media_backup(
        source,
        tmp_path / "backups",
        now=datetime(2026, 8, 15, 3, tzinfo=timezone.utc),
    )

    archive = Path(report["archive"])
    manifest = json.loads(Path(f"{archive}.json").read_text())
    assert verify_media_archive(archive) == {"files": 2, "uncompressed_bytes": 4500}
    assert report["verified"] is True
    assert manifest["sha256"] == report["sha256"]
    assert archive.stat().st_mode & 0o777 == 0o600
    assert Path(f"{archive}.sha256").stat().st_mode & 0o777 == 0o600


def test_media_backup_refuses_symbolic_links(tmp_path):
    source = tmp_path / "uploads"
    source.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("do not archive")
    (source / "escape").symlink_to(outside)

    with pytest.raises(RuntimeError, match="symbolic links"):
        create_media_backup(source, tmp_path / "backups")


def test_media_retention_removes_only_recognized_old_backup_family(tmp_path):
    for timestamp in ("20260101_000000", "20260201_000000", "20260814_000000"):
        archive = tmp_path / f"novix_media_{timestamp}.tar.gz"
        archive.write_bytes(b"archive")
        Path(f"{archive}.sha256").write_text("checksum")
        Path(f"{archive}.json").write_text("{}")
        Path(f"{archive}.enc").write_bytes(b"encrypted")
        Path(f"{archive}.enc.sha256").write_text("checksum")
    unrelated = tmp_path / "customer-media.tar.gz"
    unrelated.write_bytes(b"keep")

    removed = prune_media_backups(
        tmp_path,
        keep_count=1,
        keep_days=30,
        now=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    assert removed == ["novix_media_20260201_000000.tar.gz", "novix_media_20260101_000000.tar.gz"]
    assert (tmp_path / "novix_media_20260814_000000.tar.gz").exists()
    assert not (tmp_path / "novix_media_20260201_000000.tar.gz.enc").exists()
    assert unrelated.exists()
