import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import PostgresClient, load_database_settings, mask_database_url, validate_database_settings


REQUIRED_TABLES = [
    "users",
    "user_ai_settings",
    "privacy_settings",
    "social_follows",
    "friendships",
    "friend_requests",
    "user_blocks",
    "user_restrictions",
    "hidden_story_authors",
    "notifications",
    "messages",
    "feed_posts",
    "feed_post_likes",
    "feed_post_saves",
    "feed_post_comments",
    "stories",
    "proof_items",
    "reports",
    "ai_core_memory",
    "ai_feed_learning",
    "verification_codes",
    "login_attempts",
    "security_events",
    "news_items",
    "realtime_presence",
    "realtime_typing",
    "call_signals",
]


def build_postgres_staging_report(environ=None, client=None):
    settings = load_database_settings(environ)
    config_issues = validate_database_settings(settings)
    blockers = []
    warnings = []

    if not settings.postgres_enabled:
        blockers.append("STORAGE_BACKEND must be postgres for staging verification.")

    blockers.extend(config_issues)

    report = {
        "ready_for_staging_database": False,
        "storage_backend": settings.storage_backend,
        "database_url": mask_database_url(settings.database_url),
        "checks": {
            "postgres_enabled": settings.postgres_enabled,
            "database_config_valid": not config_issues,
            "connection_ok": False,
            "schema_tables_present": False,
        },
        "database": {
            "name": "",
            "version": "",
        },
        "required_tables": REQUIRED_TABLES,
        "present_tables": [],
        "missing_tables": [],
        "blockers": blockers,
        "warnings": warnings,
    }

    if blockers:
        return report

    client = client or PostgresClient(settings)

    try:
        with client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), version()")
                row = cursor.fetchone()
                if row:
                    report["database"]["name"] = str(row[0])
                    report["database"]["version"] = str(row[1])

                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    """
                )
                present_tables = sorted(str(item[0]) for item in cursor.fetchall())
    except Exception as error:
        report["blockers"].append(f"Could not verify PostgreSQL staging database: {error}")
        return report

    missing_tables = [table for table in REQUIRED_TABLES if table not in present_tables]

    report["checks"]["connection_ok"] = True
    report["present_tables"] = present_tables
    report["missing_tables"] = missing_tables
    report["checks"]["schema_tables_present"] = not missing_tables
    if missing_tables:
        report["blockers"].append("Missing required tables. Apply database/migrations/001_initial_schema.sql first.")

    report["ready_for_staging_database"] = not report["blockers"]
    return report


def main():
    parser = argparse.ArgumentParser(description="Verify PostgreSQL/Supabase staging database readiness.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    report = build_postgres_staging_report()
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
