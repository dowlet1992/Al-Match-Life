from scripts.check_postgres_staging import REQUIRED_TABLES, build_postgres_staging_report


class FakeCursor:
    def __init__(self, tables=None):
        self.tables = tables or []
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchone(self):
        return ("staging_db", "PostgreSQL 16 test")

    def fetchall(self):
        return [(table,) for table in self.tables]


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


class FakeClient:
    def __init__(self, tables=None, error=None):
        self.cursor = FakeCursor(tables)
        self.error = error

    def connect(self):
        if self.error:
            raise self.error
        return FakeConnection(self.cursor)


def postgres_env():
    return {
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:secret@example.com/db",
    }


def test_postgres_staging_check_requires_postgres_backend():
    report = build_postgres_staging_report({"STORAGE_BACKEND": "json"})

    assert report["ready_for_staging_database"] is False
    assert "STORAGE_BACKEND must be postgres for staging verification." in report["blockers"]


def test_postgres_staging_check_reports_missing_tables():
    report = build_postgres_staging_report(postgres_env(), client=FakeClient(tables=["users"]))

    assert report["checks"]["connection_ok"] is True
    assert report["ready_for_staging_database"] is False
    assert "messages" in report["missing_tables"]
    assert "secret" not in report["database_url"]


def test_postgres_staging_check_passes_when_all_tables_exist():
    report = build_postgres_staging_report(postgres_env(), client=FakeClient(tables=REQUIRED_TABLES))

    assert report["ready_for_staging_database"] is True
    assert report["checks"]["schema_tables_present"] is True
    assert report["missing_tables"] == []
    assert report["database"]["name"] == "staging_db"


def test_postgres_staging_check_reports_connection_failure():
    report = build_postgres_staging_report(postgres_env(), client=FakeClient(error=RuntimeError("network failed")))

    assert report["ready_for_staging_database"] is False
    assert "network failed" in report["blockers"][0]
