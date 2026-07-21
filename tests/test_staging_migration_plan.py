import json

from scripts.staging_migration_plan import build_staging_migration_plan


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_project_files(root):
    write_json(root / "users.json", [{"email": "alice@example.com"}])
    write_json(root / "messages.json", [])
    write_json(root / "database" / "feed_data.json", {"posts": []})
    schema_path = root / "database" / "migrations" / "001_initial_schema.sql"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text("CREATE TABLE IF NOT EXISTS users (id TEXT);\n", encoding="utf-8")
    import_path = root / "database" / "import" / "generated_import.sql"
    import_path.parent.mkdir(parents=True, exist_ok=True)
    import_path.write_text("BEGIN;\nINSERT INTO users (email) VALUES ('a@example.com');\nCOMMIT;\n", encoding="utf-8")


def test_staging_migration_plan_reports_json_ready_but_blocks_without_postgres(tmp_path):
    write_project_files(tmp_path)

    plan = build_staging_migration_plan(tmp_path, environ={"STORAGE_BACKEND": "json"})

    assert plan["ready_to_run_against_staging"] is False
    assert plan["steps"][0]["id"] == "json_readiness"
    assert plan["steps"][0]["ready"] is True
    assert "STORAGE_BACKEND must be postgres before applying schema." in plan["blockers"]
    assert "STORAGE_BACKEND must be postgres before applying import SQL." in plan["blockers"]


def test_staging_migration_plan_is_json_serializable(tmp_path):
    write_project_files(tmp_path)

    plan = build_staging_migration_plan(tmp_path, environ={"STORAGE_BACKEND": "json"})

    json.dumps(plan)


def test_staging_migration_plan_includes_expected_commands(tmp_path):
    write_project_files(tmp_path)

    plan = build_staging_migration_plan(tmp_path, environ={"STORAGE_BACKEND": "json"})
    commands = [step["command"] for step in plan["steps"]]

    assert "python3 scripts/check_database_readiness.py --pretty" in commands
    assert "python3 scripts/apply_postgres_schema.py --apply --pretty" in commands
    assert "python3 scripts/apply_postgres_import.py --apply --pretty" in commands
    assert "python3 scripts/check_postgres_staging.py --pretty" in commands
    assert "python3 scripts/check_postgres_staging.py --verify-data --pretty" in commands
