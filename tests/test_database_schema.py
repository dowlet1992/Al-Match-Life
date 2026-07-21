from pathlib import Path


SCHEMA_PATH = Path("database/migrations/001_initial_schema.sql")


def test_initial_database_schema_contains_core_tables():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    required_tables = [
        "users",
        "auth_refresh_sessions",
        "user_ai_settings",
        "privacy_settings",
        "social_follows",
        "friendships",
        "friend_requests",
        "notifications",
        "messages",
        "feed_posts",
        "stories",
        "proof_items",
        "ai_core_memory",
        "ai_feed_learning",
        "security_events",
        "call_signals",
        "rate_limit_buckets",
    ]

    assert "CREATE EXTENSION IF NOT EXISTS pgcrypto" in schema
    for table_name in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in schema


def test_initial_database_schema_has_important_indexes():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "idx_notifications_user_created" in schema
    assert "idx_messages_conversation" in schema
    assert "idx_feed_posts_created" in schema
    assert "idx_security_events_email_created" in schema
    assert "idx_rate_limit_buckets_expires" in schema


def test_feed_post_identifiers_match_web_route_contract():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    assert "id BIGINT PRIMARY KEY" in schema
    assert schema.count("post_id BIGINT NOT NULL REFERENCES feed_posts(id)") == 3
