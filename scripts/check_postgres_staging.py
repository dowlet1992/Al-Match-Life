import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import PostgresClient, load_database_settings, mask_database_url, validate_database_settings
from scripts.build_json_import_plan import build_import_plan


REQUIRED_TABLES = [
    "users",
    "auth_refresh_sessions",
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
    "rate_limit_buckets",
    "push_devices",
    "call_push_outbox",
    "call_push_deliveries",
]

REQUIRED_COLUMN_TYPES = {
    "users": {"id": "uuid", "email": "text", "password_hash": "text"},
    "auth_refresh_sessions": {"token_id": "text", "family_id": "text", "user_id": "uuid", "token_hash": "text"},
    "user_ai_settings": {"user_id": "uuid", "settings": "jsonb"},
    "privacy_settings": {"user_id": "uuid", "show_in_search": "bool"},
    "social_follows": {"follower_id": "uuid", "following_id": "uuid"},
    "friendships": {"user_low_id": "uuid", "user_high_id": "uuid"},
    "friend_requests": {"id": "uuid", "sender_id": "uuid", "receiver_id": "uuid"},
    "user_blocks": {"blocker_id": "uuid", "blocked_id": "uuid"},
    "user_restrictions": {"restrictor_id": "uuid", "restricted_id": "uuid"},
    "hidden_story_authors": {"viewer_id": "uuid", "author_id": "uuid"},
    "notifications": {"id": "uuid", "user_id": "uuid"},
    "messages": {"id": "int8", "sender_id": "uuid", "receiver_id": "uuid", "source_language": "text", "translations": "jsonb"},
    "feed_posts": {"id": "int8", "author_id": "uuid"},
    "feed_post_likes": {"post_id": "int8", "user_id": "uuid"},
    "feed_post_saves": {"post_id": "int8", "user_id": "uuid"},
    "feed_post_comments": {"id": "uuid", "post_id": "int8", "user_id": "uuid"},
    "stories": {"id": "uuid", "author_id": "uuid"},
    "proof_items": {"id": "uuid", "user_id": "uuid"},
    "reports": {"id": "uuid", "reporter_id": "uuid", "target_user_id": "uuid"},
    "ai_core_memory": {"id": "uuid", "user_id": "uuid"},
    "ai_feed_learning": {"user_id": "uuid", "actions": "jsonb"},
    "verification_codes": {"key": "text", "code_hash": "text"},
    "login_attempts": {"key": "text", "attempts": "jsonb"},
    "security_events": {"id": "int8", "event": "text"},
    "news_items": {"id": "uuid", "media": "jsonb"},
    "realtime_presence": {"user_id": "uuid", "online": "bool"},
    "realtime_typing": {"sender_id": "uuid", "receiver_id": "uuid"},
    "call_signals": {"room_id": "text", "payload": "jsonb"},
    "rate_limit_buckets": {"key_hash": "text", "category": "text", "bucket_start": "bigint", "request_count": "integer", "expires_at": "timestamp with time zone"},
    "push_devices": {"id": "uuid", "user_id": "uuid", "device_id": "text", "platform": "text", "token_hash": "text"},
    "call_push_outbox": {"event_id": "text", "target_user_id": "uuid", "payload": "jsonb", "status": "text", "attempts": "integer"},
    "call_push_deliveries": {"event_id": "text", "device_id": "uuid", "status": "text", "attempts": "integer"},
}


def build_postgres_staging_report(environ=None, client=None, root=".", verify_data=False):
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
            "schema_columns_valid": False,
            "data_counts_match": False if verify_data else None,
        },
        "database": {
            "name": "",
            "version": "",
        },
        "required_tables": REQUIRED_TABLES,
        "present_tables": [],
        "missing_tables": [],
        "column_issues": [],
        "verify_data": verify_data,
        "expected_row_counts": {},
        "actual_row_counts": {},
        "row_count_mismatches": {},
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

                cursor.execute(
                    """
                    SELECT table_name, column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    """
                )
                present_columns = {
                    (str(table), str(column)): str(udt_name)
                    for table, column, udt_name in cursor.fetchall()
                }
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

    column_issues = []
    if not missing_tables:
        for table, columns in REQUIRED_COLUMN_TYPES.items():
            for column, expected_type in columns.items():
                actual_type = present_columns.get((table, column))
                if actual_type is None:
                    column_issues.append({"table": table, "column": column, "issue": "missing", "expected_type": expected_type})
                elif actual_type != expected_type:
                    column_issues.append({
                        "table": table, "column": column, "issue": "wrong_type",
                        "expected_type": expected_type, "actual_type": actual_type,
                    })

    report["column_issues"] = column_issues
    report["checks"]["schema_columns_valid"] = not missing_tables and not column_issues
    if column_issues:
        report["blockers"].append("Required PostgreSQL columns or data types do not match the application contract.")

    if verify_data and not report["blockers"]:
        import_plan = build_import_plan(root)
        expected_counts = import_plan.get("row_counts", {})
        count_query = " UNION ALL ".join(
            f"SELECT '{table}' AS table_name, COUNT(*)::bigint AS row_count FROM {table}"
            for table in REQUIRED_TABLES
        )
        try:
            with client.connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(count_query)
                    actual_counts = {str(table): int(count) for table, count in cursor.fetchall()}
        except Exception as error:
            report["blockers"].append(f"Could not verify imported row counts: {error}")
            actual_counts = {}

        mismatches = {
            table: {"expected": int(expected_counts.get(table, 0)), "actual": int(actual_counts.get(table, 0))}
            for table in REQUIRED_TABLES
            if int(actual_counts.get(table, 0)) != int(expected_counts.get(table, 0))
        }
        report["expected_row_counts"] = expected_counts
        report["actual_row_counts"] = actual_counts
        report["row_count_mismatches"] = mismatches
        report["checks"]["data_counts_match"] = not mismatches and not report["blockers"]
        if mismatches:
            report["blockers"].append("Imported PostgreSQL row counts do not match the JSON import plan.")

    report["ready_for_staging_database"] = not report["blockers"]
    return report


def main():
    parser = argparse.ArgumentParser(description="Verify PostgreSQL/Supabase staging database readiness.")
    parser.add_argument("--root", default=".", help="Project root containing the JSON import source.")
    parser.add_argument("--verify-data", action="store_true", help="Require imported table counts to match the JSON import plan.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    report = build_postgres_staging_report(root=args.root, verify_data=args.verify_data)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
