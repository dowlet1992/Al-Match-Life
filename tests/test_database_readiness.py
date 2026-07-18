import json

from scripts.check_database_readiness import build_readiness_report


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_database_readiness_allows_clean_json_mode(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "messages.json", [])
    write_json(tmp_path / "database" / "feed_data.json", {"posts": []})
    write_json(tmp_path / "database" / "migrations" / "001_initial_schema.sql", "-- schema")

    report = build_readiness_report(tmp_path, {"STORAGE_BACKEND": "json"})

    assert report["ready_for_staging_import"] is True
    assert report["storage_backend"] == "json"
    assert report["checks"]["migration_schema_exists"] is True


def test_database_readiness_blocks_invalid_postgres_config(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "database" / "migrations" / "001_initial_schema.sql", "-- schema")

    report = build_readiness_report(tmp_path, {"STORAGE_BACKEND": "postgres"})

    assert report["ready_for_staging_import"] is False
    assert "DATABASE_URL is required when STORAGE_BACKEND=postgres." in report["blockers"]


def test_database_readiness_masks_database_url(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "database" / "migrations" / "001_initial_schema.sql", "-- schema")

    report = build_readiness_report(tmp_path, {
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:secret@example.com/db",
    })

    assert report["database_url"] == "postgresql://user:***@example.com/db"
