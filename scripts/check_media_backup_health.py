#!/usr/bin/env python3
"""Validate NOVIX media-backup freshness, checksum, and archive manifest."""

import argparse
import json
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_media import ARCHIVE_NAME, verify_media_archive
from scripts.backup_postgres import file_sha256


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def build_media_backup_health_report(output_dir, max_age_hours=26, now=None):
    output_dir = Path(output_dir).resolve()
    now = now or datetime.now(timezone.utc)
    max_age_hours = max(1, int(max_age_hours))
    candidates = []
    for path in output_dir.iterdir() if output_dir.exists() else ():
        match = ARCHIVE_NAME.fullmatch(path.name)
        if path.is_file() and match:
            created_at = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            candidates.append((created_at, path))
    created_at, archive = max(candidates, default=(None, None))
    blockers = []
    report = {
        "ready": False,
        "checked_at": now.isoformat(),
        "max_age_hours": max_age_hours,
        "latest_archive": archive.name if archive else None,
        "age_hours": None,
        "bytes": None,
        "files": None,
        "checksum_valid": False,
        "archive_verified": False,
        "blockers": blockers,
    }
    if archive is None:
        blockers.append("No NOVIX media backup archive found.")
        return report
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    report["age_hours"] = round(age_hours, 2)
    report["bytes"] = archive.stat().st_size
    if age_hours > max_age_hours:
        blockers.append("Latest media backup is stale.")

    checksum_path = Path(f"{archive}.sha256")
    expected = None
    if checksum_path.exists():
        parts = checksum_path.read_text(encoding="utf-8").strip().split()
        if len(parts) == 2 and SHA256.fullmatch(parts[0]) and parts[1] == archive.name:
            expected = parts[0]
    actual = file_sha256(archive)
    report["checksum_valid"] = bool(expected and expected == actual)
    if not report["checksum_valid"]:
        blockers.append("Latest media backup checksum is missing or invalid.")

    manifest = None
    manifest_path = Path(f"{archive}.json")
    if manifest_path.exists():
        try:
            candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = candidate if isinstance(candidate, dict) else None
        except json.JSONDecodeError:
            pass
    try:
        verification = verify_media_archive(archive)
    except (OSError, tarfile.TarError, RuntimeError):
        verification = None
    report["files"] = verification.get("files") if verification else None
    report["archive_verified"] = bool(
        manifest
        and verification
        and manifest.get("archive") == archive.name
        and manifest.get("bytes") == archive.stat().st_size
        and manifest.get("sha256") == actual
        and manifest.get("verified") is True
        and manifest.get("files") == verification["files"]
        and manifest.get("uncompressed_bytes") == verification["uncompressed_bytes"]
    )
    if not report["archive_verified"]:
        blockers.append("Latest media backup archive or manifest verification failed.")
    report["ready"] = not blockers
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check NOVIX user-media backup health.")
    parser.add_argument("--output-dir", default="backups/media")
    parser.add_argument("--max-age-hours", type=int, default=26)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    report = build_media_backup_health_report(args.output_dir, args.max_age_hours)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
