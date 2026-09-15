import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
ARCHIVE_NAME = re.compile(r"^novix_(\d{8}_\d{6})\.dump$")


def safe_name(value, label):
    value = str(value or "").strip()
    if not value or not SAFE_NAME.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def run(command, capture=False):
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=capture,
    )


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prune_backups(output_dir, keep_count=14, keep_days=30, now=None):
    """Remove only recognized NOVIX archives outside the configured retention window."""
    output_dir = Path(output_dir).resolve()
    keep_count = max(1, int(keep_count))
    keep_days = max(1, int(keep_days))
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=keep_days)
    archives = []
    for path in output_dir.iterdir():
        match = ARCHIVE_NAME.fullmatch(path.name)
        if not match or not path.is_file():
            continue
        created_at = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        archives.append((created_at, path))
    archives.sort(reverse=True)
    removed = []
    for index, (created_at, archive) in enumerate(archives):
        if index < keep_count or created_at >= cutoff:
            continue
        encrypted = Path(f"{archive}.enc")
        for candidate in (
            archive,
            archive.with_suffix(".dump.sha256"),
            archive.with_suffix(".dump.json"),
            encrypted,
            Path(f"{encrypted}.sha256"),
        ):
            if candidate.exists() and candidate.is_file():
                candidate.unlink()
        removed.append(archive.name)
    return removed


def create_backup(
    container,
    database,
    user,
    output_dir,
    verify=False,
    now=None,
    runner=run,
    keep_count=14,
    keep_days=30,
):
    container = safe_name(container, "container")
    database = safe_name(database, "database")
    user = safe_name(user, "database user")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    archive_name = f"novix_{timestamp}.dump"
    container_archive = f"/tmp/{archive_name}"
    output_path = output_dir / archive_name
    partial_path = output_dir / f".{archive_name}.partial"
    restore_database = safe_name(f"novix_restore_check_{timestamp}", "restore database")
    verified = False
    counts = {}

    runner(["docker", "exec", container, "pg_dump", "-U", user, "-d", database, "-Fc", "-f", container_archive])
    try:
        runner(["docker", "cp", f"{container}:{container_archive}", str(partial_path)])
        if not partial_path.exists() or partial_path.stat().st_size < 1024:
            raise RuntimeError("PostgreSQL backup archive is missing or unexpectedly small")
        partial_path.chmod(0o600)
        os.replace(partial_path, output_path)
        if verify:
            runner(["docker", "exec", container, "dropdb", "-U", user, "--if-exists", restore_database])
            try:
                runner(["docker", "exec", container, "createdb", "-U", user, restore_database])
                runner(["docker", "exec", container, "pg_restore", "-U", user, "-d", restore_database, container_archive])
                result = runner([
                    "docker", "exec", container, "psql", "-U", user, "-d", restore_database,
                    "-Atc", "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'; SELECT count(*) FROM users; SELECT count(*) FROM messages; SELECT count(*) FROM feed_posts;",
                ], capture=True)
                values = [int(value) for value in result.stdout.splitlines() if value.strip().isdigit()]
                if len(values) != 4 or values[0] < 1:
                    raise RuntimeError("Restored database verification returned invalid counts")
                counts = dict(zip(("tables", "users", "messages", "feed_posts"), values))
                verified = True
            finally:
                runner(["docker", "exec", container, "dropdb", "-U", user, "--if-exists", restore_database])
    finally:
        partial_path.unlink(missing_ok=True)
        runner(["docker", "exec", container, "rm", "-f", container_archive])

    checksum = file_sha256(output_path)
    checksum_path = output_path.with_suffix(".dump.sha256")
    manifest_path = output_path.with_suffix(".dump.json")
    checksum_path.write_text(f"{checksum}  {archive_name}\n", encoding="utf-8")
    manifest = {
        "format_version": 1,
        "created_at": (now or datetime.now(timezone.utc)).isoformat(),
        "database": database,
        "archive": archive_name,
        "bytes": output_path.stat().st_size,
        "sha256": checksum,
        "restore_verified": verified,
        "restored_counts": counts,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksum_path.chmod(0o600)
    manifest_path.chmod(0o600)
    removed = prune_backups(output_dir, keep_count=keep_count, keep_days=keep_days, now=now)

    return {
        "ok": True,
        "archive": str(output_path),
        "bytes": output_path.stat().st_size,
        "sha256": checksum,
        "checksum_file": str(checksum_path),
        "manifest": str(manifest_path),
        "verified": verified,
        "restored_counts": counts,
        "retention_removed": removed,
    }


def main():
    parser = argparse.ArgumentParser(description="Create and optionally restore-verify a NOVIX PostgreSQL backup.")
    parser.add_argument("--container", default="novix-postgres-staging")
    parser.add_argument("--database", default="novix")
    parser.add_argument("--user", default="novix")
    parser.add_argument("--output-dir", default="backups/postgres")
    parser.add_argument("--keep-count", type=int, default=14)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    report = create_backup(
        args.container,
        args.database,
        args.user,
        args.output_dir,
        verify=args.verify,
        keep_count=args.keep_count,
        keep_days=args.keep_days,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
