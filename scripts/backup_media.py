#!/usr/bin/env python3
"""Create an atomic, verified, compressed backup of NOVIX user media."""

import argparse
import json
import os
import re
import sys
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backup_postgres import file_sha256


ARCHIVE_NAME = re.compile(r"^novix_media_(\d{8}_\d{6})\.tar\.gz$")


def source_files(source):
    source = Path(source).resolve()
    if not source.is_dir():
        raise RuntimeError("Media source directory does not exist")
    files = []
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("Media backup refuses symbolic links")
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise RuntimeError("Media backup supports only regular files and directories")
    return source, files


def normalized_tar_info(info):
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mode = 0o600
    return info


def verify_media_archive(path):
    path = Path(path).resolve()
    names = set()
    files = 0
    total_bytes = 0
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            member_path = PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts or not member.isreg():
                raise RuntimeError("Media archive contains an unsafe member")
            if member.name in names:
                raise RuntimeError("Media archive contains a duplicate member")
            names.add(member.name)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError("Media archive member cannot be read")
            observed = 0
            for chunk in iter(lambda: extracted.read(1024 * 1024), b""):
                observed += len(chunk)
            if observed != member.size:
                raise RuntimeError("Media archive member size is invalid")
            files += 1
            total_bytes += observed
    return {"files": files, "uncompressed_bytes": total_bytes}


def prune_media_backups(output_dir, keep_count=14, keep_days=30, now=None):
    output_dir = Path(output_dir).resolve()
    keep_count = max(1, int(keep_count))
    keep_days = max(1, int(keep_days))
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=keep_days)
    archives = []
    for path in output_dir.iterdir() if output_dir.exists() else ():
        match = ARCHIVE_NAME.fullmatch(path.name)
        if path.is_file() and match:
            created_at = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            archives.append((created_at, path))
    archives.sort(reverse=True)
    removed = []
    for index, (created_at, archive) in enumerate(archives):
        if index < keep_count or created_at >= cutoff:
            continue
        for candidate in (
            archive,
            Path(f"{archive}.sha256"),
            Path(f"{archive}.json"),
            Path(f"{archive}.enc"),
            Path(f"{archive}.enc.sha256"),
        ):
            if candidate.is_file():
                candidate.unlink()
        removed.append(archive.name)
    return removed


def create_media_backup(source, output_dir, *, now=None, keep_count=14, keep_days=30):
    source, files = source_files(source)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = now or datetime.now(timezone.utc)
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    archive = output_dir / f"novix_media_{timestamp}.tar.gz"
    partial = output_dir / f".{archive.name}.partial"
    if archive.exists():
        raise RuntimeError("Media backup archive already exists")
    try:
        with tarfile.open(partial, "w:gz", compresslevel=6) as destination:
            for path in files:
                destination.add(
                    path,
                    arcname=path.relative_to(source).as_posix(),
                    recursive=False,
                    filter=normalized_tar_info,
                )
        partial.chmod(0o600)
        os.replace(partial, archive)
    finally:
        partial.unlink(missing_ok=True)

    verification = verify_media_archive(archive)
    if verification["files"] != len(files):
        archive.unlink(missing_ok=True)
        raise RuntimeError("Media backup verification count does not match the source")
    checksum = file_sha256(archive)
    checksum_path = Path(f"{archive}.sha256")
    manifest_path = Path(f"{archive}.json")
    checksum_path.write_text(f"{checksum}  {archive.name}\n", encoding="utf-8")
    manifest_path.write_text(json.dumps({
        "format_version": 1,
        "created_at": created_at.isoformat(),
        "archive": archive.name,
        "bytes": archive.stat().st_size,
        "sha256": checksum,
        "verified": True,
        **verification,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksum_path.chmod(0o600)
    manifest_path.chmod(0o600)
    removed = prune_media_backups(
        output_dir,
        keep_count=keep_count,
        keep_days=keep_days,
        now=created_at,
    )
    return {
        "ok": True,
        "archive": str(archive),
        "bytes": archive.stat().st_size,
        "sha256": checksum,
        "verified": True,
        **verification,
        "retention_removed": removed,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create a verified NOVIX user-media backup.")
    parser.add_argument("--source", default="uploads")
    parser.add_argument("--output-dir", default="backups/media")
    parser.add_argument("--keep-count", type=int, default=14)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = create_media_backup(
            args.source,
            args.output_dir,
            keep_count=args.keep_count,
            keep_days=args.keep_days,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
