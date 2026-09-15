#!/usr/bin/env python3
"""Validate freshness, integrity, restore evidence, and job audit for PostgreSQL backups."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_postgres import ARCHIVE_NAME, file_sha256


SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _latest_archive(output_dir):
    archives = []
    for path in output_dir.iterdir() if output_dir.exists() else ():
        match = ARCHIVE_NAME.fullmatch(path.name)
        if path.is_file() and match:
            created_at = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            archives.append((created_at, path))
    return max(archives, default=(None, None))


def _latest_audit_record(path):
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    try:
        record = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def build_backup_health_report(output_dir, max_age_hours=26, now=None):
    output_dir = Path(output_dir).resolve()
    now = now or datetime.now(timezone.utc)
    max_age_hours = max(1, int(max_age_hours))
    blockers = []
    archive_created_at, archive = _latest_archive(output_dir)
    report = {
        "ready": False,
        "checked_at": now.isoformat(),
        "max_age_hours": max_age_hours,
        "latest_archive": archive.name if archive else None,
        "age_hours": None,
        "bytes": None,
        "checksum_valid": False,
        "restore_verified": False,
        "audit_matches": False,
        "encrypted_export_present": False,
        "encrypted_export_valid": None,
        "blockers": blockers,
    }
    if archive is None:
        blockers.append("No NOVIX PostgreSQL backup archive found.")
        return report

    age_hours = max(0.0, (now - archive_created_at).total_seconds() / 3600)
    report["age_hours"] = round(age_hours, 2)
    report["bytes"] = archive.stat().st_size
    if age_hours > max_age_hours:
        blockers.append("Latest PostgreSQL backup is stale.")
    if archive.stat().st_size < 1024:
        blockers.append("Latest PostgreSQL backup is unexpectedly small.")

    checksum_path = archive.with_suffix(".dump.sha256")
    expected_checksum = None
    if checksum_path.exists():
        parts = checksum_path.read_text(encoding="utf-8").strip().split()
        if len(parts) == 2 and SHA256.fullmatch(parts[0]) and parts[1] == archive.name:
            expected_checksum = parts[0]
    actual_checksum = file_sha256(archive)
    report["checksum_valid"] = bool(expected_checksum and expected_checksum == actual_checksum)
    if not report["checksum_valid"]:
        blockers.append("Latest PostgreSQL backup checksum is missing or invalid.")

    manifest_path = archive.with_suffix(".dump.json")
    manifest = None
    if manifest_path.exists():
        try:
            candidate = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = candidate if isinstance(candidate, dict) else None
        except json.JSONDecodeError:
            pass
    report["restore_verified"] = bool(
        manifest
        and manifest.get("archive") == archive.name
        and manifest.get("bytes") == archive.stat().st_size
        and manifest.get("sha256") == actual_checksum
        and manifest.get("restore_verified") is True
    )
    if not report["restore_verified"]:
        blockers.append("Latest PostgreSQL backup has no valid restore verification manifest.")

    audit = _latest_audit_record(output_dir / "backup-jobs.jsonl")
    report["audit_matches"] = bool(
        audit
        and audit.get("ok") is True
        and audit.get("archive") == archive.name
        and audit.get("sha256") == actual_checksum
        and audit.get("restore_verified") is True
    )
    if not report["audit_matches"]:
        blockers.append("Latest PostgreSQL backup does not match the successful job audit record.")

    encrypted_name = audit.get("encrypted_archive") if audit else None
    if encrypted_name:
        encrypted_path = output_dir / Path(encrypted_name).name
        encrypted_checksum_path = Path(f"{encrypted_path}.sha256")
        report["encrypted_export_present"] = encrypted_path.is_file()
        expected_encrypted_checksum = None
        if encrypted_checksum_path.exists():
            parts = encrypted_checksum_path.read_text(encoding="utf-8").strip().split()
            if len(parts) == 2 and SHA256.fullmatch(parts[0]) and parts[1] == encrypted_path.name:
                expected_encrypted_checksum = parts[0]
        report["encrypted_export_valid"] = bool(
            encrypted_path.is_file()
            and expected_encrypted_checksum
            and expected_encrypted_checksum == file_sha256(encrypted_path)
            and expected_encrypted_checksum == audit.get("encrypted_sha256")
        )
        if not report["encrypted_export_valid"]:
            blockers.append("Encrypted off-site backup export is missing or has an invalid checksum.")

    report["ready"] = not blockers
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check NOVIX PostgreSQL backup health.")
    parser.add_argument("--output-dir", default="backups/postgres")
    parser.add_argument("--max-age-hours", type=int, default=26)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    report = build_backup_health_report(args.output_dir, max_age_hours=args.max_age_hours)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
