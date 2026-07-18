from backend.database import DatabaseSettings
from backend.repositories.social_safety_repository import (
    JsonRelationshipMapRepository,
    JsonReportsRepository,
    PostgresRelationshipMapRepository,
    PostgresReportsRepository,
    get_blocks_repository,
    get_reports_repository,
    normalize_relationship_map,
    normalize_reports_data,
)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows


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
    def __init__(self, rows=None):
        self.cursor = FakeCursor(rows)
        self.connection = FakeConnection(self.cursor)

    def connect(self):
        return self.connection


def test_relationship_map_normalizer_accepts_legacy_plain_dict():
    data = normalize_relationship_map({
        "Alice@Example.com": ["Bob@Example.com", "bob@example.com", "alice@example.com", ""],
    }, "blocks")

    assert data == {"blocks": {"alice@example.com": ["bob@example.com"]}}


def test_reports_normalizer_requires_report_list():
    assert normalize_reports_data({"reports": {}}) == {"reports": []}


def test_json_relationship_map_repository_round_trip(tmp_path):
    repository = JsonRelationshipMapRepository(tmp_path / "blocks.json", "blocks")

    repository.save_all({"blocks": {"alice@example.com": ["bob@example.com"]}})

    assert repository.load_all() == {"blocks": {"alice@example.com": ["bob@example.com"]}}


def test_json_reports_repository_round_trip(tmp_path):
    repository = JsonReportsRepository(tmp_path / "reports.json")
    data = {
        "reports": [{
            "id": "report-1",
            "reporter_email": "alice@example.com",
            "target_email": "bob@example.com",
            "reason": "spam",
            "details": "Bad content",
            "status": "new",
            "created_at": "2026-01-01 10:00:00",
        }]
    }

    repository.save_all(data)

    report = repository.load_all()["reports"][0]
    assert report["id"] == "report-1"
    assert report["reporter_email"] == "alice@example.com"
    assert report["target_email"] == "bob@example.com"
    assert report["status"] == "new"
    assert report["moderation_note"] == ""


def test_postgres_relationship_map_repository_loads_rows():
    client = FakeClient(rows=[("alice@example.com", "bob@example.com")])
    repository = PostgresRelationshipMapRepository(
        "user_blocks", "blocker_id", "blocked_id", "blocks", client=client
    )

    assert repository.load_all() == {"blocks": {"alice@example.com": ["bob@example.com"]}}
    assert "FROM user_blocks" in client.cursor.calls[0][0]


def test_postgres_relationship_map_repository_saves_rows():
    client = FakeClient()
    repository = PostgresRelationshipMapRepository(
        "user_blocks", "blocker_id", "blocked_id", "blocks", client=client
    )

    repository.save_all({"blocks": {"alice@example.com": ["bob@example.com"]}})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM user_blocks"
    assert "INSERT INTO user_blocks" in client.cursor.calls[1][0]


def test_postgres_reports_repository_loads_reports():
    client = FakeClient(rows=[
        (
            "report-id", "alice@example.com", "bob@example.com", "spam", "Bad content", "new",
            "2026-01-01", "2026-01-02", "admin@example.com", "2026-01-02", "Handled", "warning_sent",
        )
    ])
    repository = PostgresReportsRepository(client=client)

    data = repository.load_all()

    assert data["reports"][0]["reporter_email"] == "alice@example.com"
    assert data["reports"][0]["target_email"] == "bob@example.com"
    assert data["reports"][0]["reason"] == "spam"
    assert data["reports"][0]["reviewed_by"] == "admin@example.com"
    assert data["reports"][0]["moderation_note"] == "Handled"


def test_postgres_reports_repository_saves_reports():
    client = FakeClient()
    repository = PostgresReportsRepository(client=client)

    repository.save_all({
        "reports": [{
            "reporter_email": "alice@example.com",
            "target_email": "bob@example.com",
            "reason": "spam",
            "details": "Bad content",
            "status": "new",
            "created_at": "",
        }]
    })

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM reports"
    assert "INSERT INTO reports" in client.cursor.calls[1][0]
    assert client.cursor.calls[1][1]["created_at"] is None


def test_get_social_safety_repositories_use_postgres_for_default_files():
    settings = DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://user:pass@example.com/db",
    )

    blocks_repository = get_blocks_repository(settings=settings, client=FakeClient())
    reports_repository = get_reports_repository(settings=settings, client=FakeClient())

    assert isinstance(blocks_repository, PostgresRelationshipMapRepository)
    assert isinstance(reports_repository, PostgresReportsRepository)
