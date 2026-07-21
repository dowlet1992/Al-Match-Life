import json

from scripts.apply_postgres_schema import build_schema_apply_report, count_schema_statements


class FakeCursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True


class FakeClient:
    def __init__(self):
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)

    def connect(self):
        return self.connection


def write_schema(root, sql="CREATE TABLE IF NOT EXISTS users (id TEXT);\n"):
    path = root / "database" / "migrations" / "001_initial_schema.sql"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")


def postgres_env():
    return {
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:secret@example.com/db",
    }


def test_count_schema_statements_ignores_comments_and_blank_lines():
    assert count_schema_statements("""
    -- comment

    CREATE TABLE one (id TEXT);
    CREATE INDEX idx_one ON one (id);
    """) == 2


def test_schema_apply_dry_run_does_not_connect(tmp_path):
    write_schema(tmp_path)
    client = FakeClient()

    report = build_schema_apply_report(tmp_path, apply=False, environ=postgres_env(), client=client)

    assert report["dry_run"] is True
    assert report["applied"] is False
    assert report["blockers"] == []
    assert client.cursor.calls == []
    assert "secret" not in report["database_url"]


def test_schema_apply_requires_postgres_backend(tmp_path):
    write_schema(tmp_path)

    report = build_schema_apply_report(tmp_path, apply=True, environ={"STORAGE_BACKEND": "json"})

    assert report["applied"] is False
    assert "STORAGE_BACKEND must be postgres before applying schema." in report["blockers"]


def test_schema_apply_executes_and_commits_when_apply_true(tmp_path):
    schema = "CREATE TABLE IF NOT EXISTS users (id TEXT);\n"
    write_schema(tmp_path, schema)
    client = FakeClient()

    report = build_schema_apply_report(tmp_path, apply=True, environ=postgres_env(), client=client)

    assert report["applied"] is True
    assert client.cursor.calls[0][0] == schema
    assert client.connection.committed is True


def test_schema_apply_report_is_json_serializable(tmp_path):
    write_schema(tmp_path)

    report = build_schema_apply_report(tmp_path, apply=False, environ=postgres_env())

    json.dumps(report)


def test_schema_apply_discovers_ordered_incremental_migrations(tmp_path):
    write_schema(tmp_path, "CREATE TABLE first (id TEXT);\n")
    second = tmp_path / "database" / "migrations" / "002_second.sql"
    second.write_text("CREATE TABLE second (id TEXT);\n", encoding="utf-8")

    report = build_schema_apply_report(tmp_path, apply=False, environ=postgres_env())

    assert report["migration_paths"] == [
        "database/migrations/001_initial_schema.sql",
        "database/migrations/002_second.sql",
    ]
    assert report["statement_count"] == 2
