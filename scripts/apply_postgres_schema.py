import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import PostgresClient, load_database_settings, mask_database_url, validate_database_settings


DEFAULT_SCHEMA_PATH = Path("database/migrations/001_initial_schema.sql")


def load_schema_sql(root, schema_path=DEFAULT_SCHEMA_PATH):
    path = Path(root) / schema_path
    if not path.exists():
        raise FileNotFoundError(f"Missing schema file: {path}")
    migration_paths = sorted(path.parent.glob("*.sql")) if Path(schema_path) == DEFAULT_SCHEMA_PATH else [path]
    return "\n".join(item.read_text(encoding="utf-8").rstrip() for item in migration_paths) + "\n"


def count_schema_statements(schema_sql):
    statements = []
    current = []
    for line in schema_sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current).strip())
            current = []
    if current:
        statements.append("\n".join(current).strip())
    return len(statements)


def build_schema_apply_report(root=".", apply=False, environ=None, client=None):
    settings = load_database_settings(environ)
    config_issues = validate_database_settings(settings)
    blockers = []

    if not settings.postgres_enabled:
        blockers.append("STORAGE_BACKEND must be postgres before applying schema.")

    blockers.extend(config_issues)

    try:
        schema_sql = load_schema_sql(root)
        statement_count = count_schema_statements(schema_sql)
    except Exception as error:
        schema_sql = ""
        statement_count = 0
        blockers.append(str(error))

    report = {
        "applied": False,
        "dry_run": not apply,
        "storage_backend": settings.storage_backend,
        "database_url": mask_database_url(settings.database_url),
        "schema_path": str(DEFAULT_SCHEMA_PATH),
        "migration_paths": [
            str(path.relative_to(Path(root)))
            for path in sorted((Path(root) / DEFAULT_SCHEMA_PATH.parent).glob("*.sql"))
        ],
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
                cursor.execute(schema_sql)
            connection.commit()
    except Exception as error:
        report["blockers"].append(f"Could not apply PostgreSQL schema: {error}")
        return report

    report["applied"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description="Apply AI Match Life PostgreSQL schema to staging database.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--apply", action="store_true", help="Actually apply schema. Without this, only dry-run checks run.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    report = build_schema_apply_report(root=args.root, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
