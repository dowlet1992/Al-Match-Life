from backend.database import DatabaseSettings
from backend.repositories.notification_repository import (
    JsonNotificationRepository,
    PostgresNotificationRepository,
    get_notification_repository,
    normalize_notifications_data,
)
from backend.repositories.privacy_repository import (
    JsonPrivacyRepository,
    PostgresPrivacyRepository,
    get_privacy_repository,
    normalize_privacy_data,
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


def test_notification_normalizer_accepts_legacy_list():
    assert normalize_notifications_data(["hello"]) == {"notifications": ["hello"]}


def test_json_notification_repository_round_trip(tmp_path):
    repository = JsonNotificationRepository(tmp_path / "notifications.json")
    data = {"notifications": [{"email": "alice@example.com", "text": "Hi"}]}

    repository.save_all(data)

    assert repository.load_all() == data


def test_postgres_notification_repository_loads_notifications():
    client = FakeClient(rows=[
        ("alice@example.com", "bob@example.com", "follow", "Bob followed you", "", False, "2026-01-01", "2026-01-01")
    ])
    repository = PostgresNotificationRepository(client=client)

    data = repository.load_all()

    assert data["notifications"][0]["email"] == "alice@example.com"
    assert data["notifications"][0]["from_email"] == "bob@example.com"
    assert data["notifications"][0]["type"] == "follow"


def test_postgres_notification_repository_saves_notifications():
    client = FakeClient()
    repository = PostgresNotificationRepository(client=client)

    repository.save_all({"notifications": [{"email": "alice@example.com", "from": "bob@example.com", "text": "Hi"}]})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM notifications"
    assert "INSERT INTO notifications" in client.cursor.calls[1][0]


def test_get_notification_repository_uses_postgres_for_default_file():
    repository = get_notification_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://example/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresNotificationRepository)


def test_privacy_normalizer_accepts_legacy_plain_dict():
    data = normalize_privacy_data({"alice@example.com": {"allow_messages": False}})

    assert data == {"users": {"alice@example.com": {"allow_messages": False}}}


def test_json_privacy_repository_round_trip(tmp_path):
    repository = JsonPrivacyRepository(tmp_path / "privacy.json")
    data = {"users": {"alice@example.com": {"allow_messages": False}}}

    repository.save_all(data)

    assert repository.load_all() == data


def test_postgres_privacy_repository_loads_settings():
    client = FakeClient(rows=[
        ("alice@example.com", True, True, False, True, False, False)
    ])
    repository = PostgresPrivacyRepository(client=client)

    data = repository.load_all()

    assert data["users"]["alice@example.com"]["show_in_search"] is False
    assert data["users"]["alice@example.com"]["allow_messages"] is True


def test_postgres_privacy_repository_saves_settings():
    client = FakeClient()
    repository = PostgresPrivacyRepository(client=client)

    repository.save_all({"users": {"alice@example.com": {"allow_messages": False}}})

    assert client.connection.committed is True
    assert "INSERT INTO privacy_settings" in client.cursor.calls[0][0]
    assert client.cursor.calls[0][1]["allow_messages"] is False


def test_get_privacy_repository_uses_postgres_for_default_file():
    repository = get_privacy_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://example/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresPrivacyRepository)
