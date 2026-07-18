import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import load_database_settings, mask_database_url, validate_database_settings
from scripts.build_json_import_plan import build_import_plan


def build_readiness_report(root, environ=None):
    root = Path(root)
    settings = load_database_settings(environ)
    import_plan = build_import_plan(root)
    migration_path = root / "database" / "migrations" / "001_initial_schema.sql"

    checks = {
        "migration_schema_exists": migration_path.exists(),
        "json_import_ready": import_plan["ready"],
        "postgres_config_valid": not validate_database_settings(settings),
        "postgres_enabled": settings.postgres_enabled,
    }

    blockers = []
    if not checks["migration_schema_exists"]:
        blockers.append("Missing database/migrations/001_initial_schema.sql.")
    if not checks["json_import_ready"]:
        blockers.append("JSON import plan has blockers.")
    blockers.extend(validate_database_settings(settings))

    return {
        "ready_for_staging_import": not blockers,
        "checks": checks,
        "storage_backend": settings.storage_backend,
        "database_url": mask_database_url(settings.database_url),
        "import_row_counts": import_plan["row_counts"],
        "blockers": blockers,
        "warnings": import_plan["warnings"],
    }


def main():
    parser = argparse.ArgumentParser(description="Check database migration readiness.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    report = build_readiness_report(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
