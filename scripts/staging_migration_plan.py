import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.apply_postgres_import import build_import_apply_report
from scripts.apply_postgres_schema import build_schema_apply_report
from scripts.check_database_readiness import build_readiness_report
from scripts.check_postgres_staging import build_postgres_staging_report


def has_blockers(report):
    return bool(report.get("blockers"))


def build_staging_migration_plan(root=".", environ=None):
    root = Path(root)

    json_readiness = build_readiness_report(root, environ=environ)
    schema_dry_run = build_schema_apply_report(root=root, apply=False, environ=environ)
    import_dry_run = build_import_apply_report(root=root, apply=False, environ=environ)
    postgres_verification = build_postgres_staging_report(environ=environ)
    final_verification = build_postgres_staging_report(environ=environ, root=root, verify_data=True)

    steps = [
        {
            "id": "json_readiness",
            "title": "Check cleaned JSON data",
            "command": "python3 scripts/check_database_readiness.py --pretty",
            "ready": not has_blockers(json_readiness),
            "blockers": json_readiness.get("blockers", []),
        },
        {
            "id": "generate_import_sql",
            "title": "Generate PostgreSQL import SQL",
            "command": "python3 scripts/export_json_to_postgres_sql.py --pretty",
            "ready": not has_blockers(json_readiness),
            "blockers": [] if not has_blockers(json_readiness) else ["JSON readiness must pass before generating import SQL."],
        },
        {
            "id": "schema_dry_run",
            "title": "Dry-run schema apply",
            "command": "python3 scripts/apply_postgres_schema.py --pretty",
            "ready": not has_blockers(schema_dry_run),
            "blockers": schema_dry_run.get("blockers", []),
        },
        {
            "id": "schema_apply",
            "title": "Apply schema to staging database",
            "command": "python3 scripts/apply_postgres_schema.py --apply --pretty",
            "ready": not has_blockers(schema_dry_run),
            "blockers": schema_dry_run.get("blockers", []),
        },
        {
            "id": "verify_staging_tables",
            "title": "Verify staging database tables",
            "command": "python3 scripts/check_postgres_staging.py --pretty",
            "ready": not has_blockers(postgres_verification),
            "blockers": postgres_verification.get("blockers", []),
        },
        {
            "id": "import_dry_run",
            "title": "Dry-run import SQL",
            "command": "python3 scripts/apply_postgres_import.py --pretty",
            "ready": not has_blockers(import_dry_run),
            "blockers": import_dry_run.get("blockers", []),
        },
        {
            "id": "import_apply",
            "title": "Apply import SQL to staging database",
            "command": "python3 scripts/apply_postgres_import.py --apply --pretty",
            "ready": not has_blockers(import_dry_run),
            "blockers": import_dry_run.get("blockers", []),
        },
        {
            "id": "final_verify",
            "title": "Final staging schema and imported data verification",
            "command": "python3 scripts/check_postgres_staging.py --verify-data --pretty",
            "ready": not has_blockers(final_verification),
            "blockers": final_verification.get("blockers", []),
        },
    ]

    blockers = []
    for step in steps:
        for blocker in step["blockers"]:
            if blocker not in blockers:
                blockers.append(blocker)

    return {
        "ready_to_run_against_staging": not blockers,
        "steps": steps,
        "reports": {
            "json_readiness": json_readiness,
            "schema_dry_run": schema_dry_run,
            "import_dry_run": import_dry_run,
            "postgres_verification": postgres_verification,
            "final_verification": final_verification,
        },
        "blockers": blockers,
    }


def main():
    parser = argparse.ArgumentParser(description="Show the full AI Match Life staging migration plan.")
    parser.add_argument("--root", default=".", help="Project root.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    plan = build_staging_migration_plan(root=args.root)
    print(json.dumps(plan, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
