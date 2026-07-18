import json

from scripts.apply_postgres_import import build_import_apply_report, load_import_sql


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


def postgres_env():
    return {
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:secret@example.com/db",
    }


def write_import(root, sql="BEGIN;\nINSERT INTO users (email) VALUES ('a@example.com');\nCOMMIT;\n"):
    path = root / "database" / "import" / "generated_import.sql"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql, encoding="utf-8")


def test_load_import_sql_requires_transaction_markers(tmp_path):
    write_import(tmp_path, "INSERT INTO users (email) VALUES ('a@example.com');\n")

    try:
        load_import_sql(tmp_path)
    except ValueError as error:
        assert "BEGIN and COMMIT" in str(error)
    else:
        raise AssertionError("Expected invalid import SQL to fail")


def test_import_apply_dry_run_does_not_connect(tmp_path):
    write_import(tmp_path)
    client = FakeClient()

    report = build_import_apply_report(tmp_path, apply=False, environ=postgres_env(), client=client)

    assert report["dry_run"] is True
    assert report["applied"] is False
    assert report["blockers"] == []
    assert client.cursor.calls == []
    assert "secret" not in report["database_url"]


def test_import_apply_requires_postgres_backend(tmp_path):
    write_import(tmp_path)

    report = build_import_apply_report(tmp_path, apply=True, environ={"STORAGE_BACKEND": "json"})

    assert report["applied"] is False
    assert "STORAGE_BACKEND must be postgres before applying import SQL." in report["blockers"]


def test_import_apply_executes_and_commits_when_apply_true(tmp_path):
    sql = "BEGIN;\nINSERT INTO users (email) VALUES ('a@example.com');\nCOMMIT;\n"
    write_import(tmp_path, sql)
    client = FakeClient()

    report = build_import_apply_report(tmp_path, apply=True, environ=postgres_env(), client=client)

    assert report["applied"] is True
    assert client.cursor.calls[0][0] == sql
    assert client.connection.committed is True


def test_import_apply_report_is_json_serializable(tmp_path):
    write_import(tmp_path)

    report = build_import_apply_report(tmp_path, apply=False, environ=postgres_env())

    json.dumps(report)
