from backend.database import DatabaseSettings
from backend.repositories.message_repository import (
    JsonMessageRepository,
    PostgresMessageRepository,
    get_message_repository,
    message_from_record,
    message_to_database_params,
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


def test_message_from_record_accepts_database_tuple():
    message = message_from_record((
        1,
        "alice@example.com",
        "bob@example.com",
        "Hello",
        "",
        "",
        "",
        None,
        "sent",
        False,
        [],
        "en",
        {"de": "Hallo"},
        "2026-01-01 10:00",
    ))

    assert message["id"] == 1
    assert message["from"] == "alice@example.com"
    assert message["to"] == "bob@example.com"
    assert message["message"] == "Hello"


def test_message_to_database_params_normalizes_email():
    params = message_to_database_params({
        "id": 1,
        "from": "ALICE@example.com",
        "to": "BOB@example.com",
        "message": "Hello",
        "deleted_for": ["alice@example.com"],
    })

    assert params["sender_email"] == "alice@example.com"
    assert params["receiver_email"] == "bob@example.com"
    assert params["deleted_for"] == ["alice@example.com"]


def test_json_message_repository_round_trip(tmp_path):
    repository = JsonMessageRepository(tmp_path / "messages.json")

    repository.save_all([{"id": 1, "message": "Hello"}])

    assert repository.load_all() == [{"id": 1, "message": "Hello"}]


def test_postgres_message_repository_loads_messages():
    client = FakeClient(rows=[(
        1,
        "alice@example.com",
        "bob@example.com",
        "Hello",
        "",
        "",
        "",
        None,
        "sent",
        False,
        [],
        "en",
        {},
        "2026-01-01 10:00",
    )])
    repository = PostgresMessageRepository(client=client)

    messages = repository.load_all()

    assert messages[0]["from"] == "alice@example.com"
    assert "FROM messages" in client.cursor.calls[0][0]


def test_postgres_message_repository_saves_messages_with_upsert():
    client = FakeClient()
    repository = PostgresMessageRepository(client=client)

    repository.save_all([{"id": 1, "from": "alice@example.com", "to": "bob@example.com", "message": "Hello"}])

    assert client.connection.committed is True
    query, params = client.cursor.calls[0]
    assert "ON CONFLICT (id) DO UPDATE" in query
    assert params["sender_email"] == "alice@example.com"


def test_get_message_repository_uses_postgres_for_default_messages_file():
    repository = get_message_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://user:pass@example.com/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresMessageRepository)


def test_get_message_repository_uses_json_for_explicit_filename(tmp_path):
    repository = get_message_repository(
        filename=tmp_path / "messages.json",
        settings=DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db"),
        client=FakeClient(),
    )

    assert isinstance(repository, JsonMessageRepository)
