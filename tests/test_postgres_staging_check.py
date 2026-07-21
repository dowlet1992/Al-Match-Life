import json

from scripts.check_postgres_staging import REQUIRED_COLUMN_TYPES, REQUIRED_TABLES, build_postgres_staging_report


class FakeCursor:
    def __init__(self, tables=None, columns=None, counts=None):
        self.tables = tables or []
        self.columns = columns if columns is not None else [
            (table, column, column_type)
            for table, required in REQUIRED_COLUMN_TYPES.items()
            for column, column_type in required.items()
        ]
        self.counts = counts or {}
        self.calls = []
        self.current_query = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))
        self.current_query = query

    def fetchone(self):
        return ("staging_db", "PostgreSQL 16 test")

    def fetchall(self):
        if "information_schema.columns" in self.current_query:
            return self.columns
        if "COUNT(*)::bigint" in self.current_query:
            return [(table, self.counts.get(table, 0)) for table in REQUIRED_TABLES]
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
    def __init__(self, tables=None, columns=None, counts=None, error=None):
        self.cursor = FakeCursor(tables, columns=columns, counts=counts)
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
    assert report["checks"]["schema_columns_valid"] is True
    assert report["missing_tables"] == []
    assert report["database"]["name"] == "staging_db"


def test_postgres_staging_check_reports_connection_failure():
    report = build_postgres_staging_report(postgres_env(), client=FakeClient(error=RuntimeError("network failed")))

    assert report["ready_for_staging_database"] is False
    assert "network failed" in report["blockers"][0]


def test_postgres_staging_check_rejects_wrong_feed_post_id_type():
    columns = [
        (table, column, "uuid" if table == "feed_posts" and column == "id" else column_type)
        for table, required in REQUIRED_COLUMN_TYPES.items()
        for column, column_type in required.items()
    ]

    report = build_postgres_staging_report(
        postgres_env(), client=FakeClient(tables=REQUIRED_TABLES, columns=columns)
    )

    assert report["ready_for_staging_database"] is False
    assert report["checks"]["schema_columns_valid"] is False
    assert report["column_issues"] == [{
        "table": "feed_posts", "column": "id", "issue": "wrong_type",
        "expected_type": "int8", "actual_type": "uuid",
    }]


def test_postgres_staging_check_verifies_imported_row_counts(tmp_path):
    (tmp_path / "users.json").write_text(json.dumps([{"email": "alice@example.com"}]), encoding="utf-8")
    counts = {table: 0 for table in REQUIRED_TABLES}
    counts["users"] = 1

    report = build_postgres_staging_report(
        postgres_env(), client=FakeClient(tables=REQUIRED_TABLES, counts=counts),
        root=tmp_path, verify_data=True,
    )

    assert report["ready_for_staging_database"] is True
    assert report["checks"]["data_counts_match"] is True
    assert report["actual_row_counts"]["users"] == 1


def test_postgres_staging_check_blocks_partial_import(tmp_path):
    (tmp_path / "users.json").write_text(json.dumps([{"email": "alice@example.com"}]), encoding="utf-8")

    report = build_postgres_staging_report(
        postgres_env(), client=FakeClient(tables=REQUIRED_TABLES),
        root=tmp_path, verify_data=True,
    )

    assert report["ready_for_staging_database"] is False
    assert report["checks"]["data_counts_match"] is False
    assert report["row_count_mismatches"]["users"] == {"expected": 1, "actual": 0}
