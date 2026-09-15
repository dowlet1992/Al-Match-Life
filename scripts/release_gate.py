#!/usr/bin/env python3
"""Run NOVIX's bounded, PII-free pre-deployment release gate."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import build_production_readiness_report, load_environment
from scripts.check_media_backup_health import build_media_backup_health_report
from scripts.check_postgres_backup_health import build_backup_health_report
from scripts.security_audit import build_security_audit


def dependency_health(runner=subprocess.run):
    result = runner(
        [sys.executable, "-m", "pip", "check"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "summary": "dependencies_consistent" if result.returncode == 0 else "dependency_conflicts_found",
    }


def build_release_gate_report(
    *,
    config_report,
    backup_report,
    media_backup_report,
    security_report,
    dependencies_report,
):
    gates = {
        "production_configuration": bool(config_report.get("ready_for_production")),
        "postgres_backup": bool(backup_report.get("ready")),
        "media_backup": bool(media_backup_report.get("ready")),
        "security_headers_and_auth": bool(security_report.get("ok")),
        "python_dependencies": bool(dependencies_report.get("ok")),
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "ready_for_release": not blockers,
        "gates": gates,
        "blockers": blockers,
        "details": {
            "production": config_report,
            "backup": backup_report,
            "media_backup": media_backup_report,
            "security": security_report,
            "dependencies": dependencies_report,
        },
    }


def guarded_report(check, failure_report):
    try:
        return check()
    except Exception as exc:
        return {**failure_report, "check_error_type": type(exc).__name__}


def run_release_gate(
    *,
    backup_dir="backups/postgres",
    media_backup_dir="backups/media",
    max_backup_age_hours=26,
):
    config_report = guarded_report(
        lambda: build_production_readiness_report(load_environment()),
        {"ready_for_production": False, "blockers": ["Production configuration check failed."]},
    )
    backup_report = guarded_report(
        lambda: build_backup_health_report(
            PROJECT_ROOT / backup_dir,
            max_age_hours=max_backup_age_hours,
        ),
        {"ready": False, "blockers": ["PostgreSQL backup health check failed."]},
    )
    media_backup_report = guarded_report(
        lambda: build_media_backup_health_report(
            PROJECT_ROOT / media_backup_dir,
            max_age_hours=max_backup_age_hours,
        ),
        {"ready": False, "blockers": ["Media backup health check failed."]},
    )
    security_report = guarded_report(
        lambda: build_security_audit(root=PROJECT_ROOT),
        {"ok": False, "checks": [], "blockers": ["Security audit failed."]},
    )
    dependencies_report = guarded_report(
        dependency_health,
        {"ok": False, "summary": "dependency_check_failed"},
    )
    return build_release_gate_report(
        config_report=config_report,
        backup_report=backup_report,
        media_backup_report=media_backup_report,
        security_report=security_report,
        dependencies_report=dependencies_report,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the NOVIX pre-deployment release gate.")
    parser.add_argument("--backup-dir", default="backups/postgres")
    parser.add_argument("--media-backup-dir", default="backups/media")
    parser.add_argument("--max-backup-age-hours", type=int, default=26)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    report = run_release_gate(
        backup_dir=args.backup_dir,
        media_backup_dir=args.media_backup_dir,
        max_backup_age_hours=args.max_backup_age_hours,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["ready_for_release"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
