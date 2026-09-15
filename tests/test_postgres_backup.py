from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.backup_postgres import create_backup, file_sha256, prune_backups, safe_name


def test_backup_rejects_shell_metacharacters():
    with pytest.raises(ValueError):
        safe_name("novix; rm", "database")


def test_backup_builds_archive_and_verifies_restore(tmp_path):
    commands = []

    def runner(command, capture=False):
        commands.append(command)
        if command[1] == "cp":
            Path(command[-1]).write_bytes(b"x" * 2048)
        return type("Result", (), {"stdout": "32\n8\n33\n6\n"})()

    report = create_backup(
        "novix-postgres-staging", "novix", "novix", tmp_path,
        verify=True, now=datetime(2026, 8, 15, 20, 0, tzinfo=timezone.utc), runner=runner,
    )

    assert report["verified"] is True
    assert report["restored_counts"] == {"tables": 32, "users": 8, "messages": 33, "feed_posts": 6}
    assert report["bytes"] == 2048
    assert report["sha256"] == file_sha256(report["archive"])
    assert Path(report["checksum_file"]).read_text().endswith("novix_20260815_200000.dump\n")
    assert Path(report["manifest"]).exists()
    assert Path(report["archive"]).stat().st_mode & 0o777 == 0o600
    assert ["docker", "exec", "novix-postgres-staging", "pg_dump", "-U", "novix", "-d", "novix", "-Fc", "-f", "/tmp/novix_20260815_200000.dump"] in commands
    assert sum(command[3] == "dropdb" for command in commands if len(command) > 3) == 2


def test_retention_only_removes_old_recognized_archives(tmp_path):
    for name in (
        "novix_20260101_000000.dump",
        "novix_20260201_000000.dump",
        "novix_20260814_000000.dump",
    ):
        archive = tmp_path / name
        archive.write_bytes(b"backup")
        archive.with_suffix(".dump.sha256").write_text("checksum")
        archive.with_suffix(".dump.json").write_text("{}")
        Path(f"{archive}.enc").write_bytes(b"encrypted")
        Path(f"{archive}.enc.sha256").write_text("encrypted-checksum")
    unrelated = tmp_path / "customer-data.dump"
    unrelated.write_bytes(b"keep")

    removed = prune_backups(
        tmp_path,
        keep_count=1,
        keep_days=30,
        now=datetime(2026, 8, 15, tzinfo=timezone.utc),
    )

    assert removed == ["novix_20260201_000000.dump", "novix_20260101_000000.dump"]
    assert (tmp_path / "novix_20260814_000000.dump").exists()
    assert not (tmp_path / "novix_20260201_000000.dump.enc").exists()
    assert not (tmp_path / "novix_20260201_000000.dump.enc.sha256").exists()
    assert unrelated.exists()
