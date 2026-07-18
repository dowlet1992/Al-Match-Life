from backend.database import DatabaseSettings
from backend.repositories.ai_memory_repository import (
    JsonAiMemoryRepository,
    PostgresAiMemoryRepository,
    get_ai_memory_repository,
)


class FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
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


def test_json_ai_memory_repository_round_trip(tmp_path):
    repository = JsonAiMemoryRepository(tmp_path / "core.json", tmp_path / "feed.json")

    repository.save_core_memory({"alice@example.com": [{"answer": "Hello"}]})
    repository.save_feed_learning({"alice@example.com": {"actions": []}})

    assert repository.load_core_memory() == {"alice@example.com": [{"answer": "Hello"}]}
    assert repository.load_feed_learning() == {"alice@example.com": {"actions": []}}


def test_postgres_ai_memory_repository_loads_core_memory():
    client = FakeClient(rows=[
        ("alice@example.com", "coach", "Question", "Answer", "2026-01-01")
    ])
    repository = PostgresAiMemoryRepository(client=client)

    data = repository.load_core_memory()

    assert data["alice@example.com"][0]["mode"] == "coach"
    assert data["alice@example.com"][0]["answer"] == "Answer"


def test_postgres_ai_memory_repository_saves_core_memory():
    client = FakeClient()
    repository = PostgresAiMemoryRepository(client=client)

    repository.save_core_memory({"alice@example.com": [{"mode": "coach", "answer": "Answer"}]})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM ai_core_memory"
    assert "INSERT INTO ai_core_memory" in client.cursor.calls[1][0]


def test_postgres_ai_memory_repository_loads_feed_learning():
    client = FakeClient(rows=[
        ("alice@example.com", {"en": 1}, {"idea": 2}, {"ai": 3}, {"Berlin": 4}, [{"type": "like"}], "2026-01-01")
    ])
    repository = PostgresAiMemoryRepository(client=client)

    data = repository.load_feed_learning()

    assert data["alice@example.com"]["languages"] == {"en": 1}
    assert data["alice@example.com"]["actions"] == [{"type": "like"}]


def test_postgres_ai_memory_repository_saves_feed_learning():
    client = FakeClient()
    repository = PostgresAiMemoryRepository(client=client)

    repository.save_feed_learning({"alice@example.com": {"languages": {"en": 1}, "actions": []}})

    assert client.connection.committed is True
    assert "INSERT INTO ai_feed_learning" in client.cursor.calls[0][0]
    assert client.cursor.calls[0][1]["languages"] == {"en": 1}


def test_get_ai_memory_repository_uses_postgres():
    repository = get_ai_memory_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://example/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresAiMemoryRepository)
