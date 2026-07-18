import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import PostgresClient, load_database_settings, mask_database_url, validate_database_settings
from scripts.apply_postgres_schema import count_schema_statements


DEFAULT_IMPORT_PATH = Path("database/import/generated_import.sql")


def load_import_sql(root, import_path=DEFAULT_IMPORT_PATH):
    path = Path(root) / import_path
    if not path.exists():
        raise FileNotFoundError(
            f"Missing import SQL file: {path}. Run scripts/export_json_to_postgres_sql.py first."
        )
    sql = path.read_text(encoding="utf-8")
    if "BEGIN;" not in sql or "COMMIT;" not in sql:
        raise ValueError("Import SQL must include BEGIN and COMMIT transaction markers.")
    return sql


def build_import_apply_report(root=".", apply=False, environ=None, client=None):
    settings = load_database_settings(environ)
    config_issues = validate_database_settings(settings)
    blockers = []

    if not settings.postgres_enabled:
        blockers.append("STORAGE_BACKEND must be postgres before applying import SQL.")

    blockers.extend(config_issues)

    try:
        import_sql = load_import_sql(root)
        statement_count = count_schema_statements(import_sql)
    except Exception as error:
        import_sql = ""
        statement_count = 0
        blockers.append(str(error))

    report = {
        "applied": False,
        "dry_run": not apply,
        "storage_backend": settings.storage_backend,
        "database_url": mask_database_url(settings.database_url),
        "import_path": str(DEFAULT_IMPORT_PATH),
        "statement_count": statement_count,
        "blockers": blockers,
    }

    if blockers:
        return report

    if not apply:
        return report

    client = client or PostgresClient(settings)

    try:
        with client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(import_sql)
            connection.commit()
    except Exception as error:
        report["blockers"].append(f"Could not apply PostgreSQL import SQL: {error}")
        return report

    report["applied"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description="Apply generated JSON import SQL to PostgreSQL staging database.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--apply", action="store_true", help="Actually apply import SQL. Without this, only dry-run checks run.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    report = build_import_apply_report(root=args.root, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
