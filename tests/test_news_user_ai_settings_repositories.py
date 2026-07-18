from backend.database import DatabaseSettings
from backend.repositories.news_repository import JsonNewsRepository, PostgresNewsRepository, get_news_repository, news_database_id
from backend.repositories.user_ai_settings_repository import (
    JsonUserAiSettingsRepository,
    PostgresUserAiSettingsRepository,
    get_user_ai_settings_repository,
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


def test_news_database_id_is_stable_for_legacy_item():
    item = {"title": "Hello", "created_at": "2026-01-01"}

    assert news_database_id(item) == news_database_id(item)


def test_json_news_repository_limits_items(tmp_path):
    repository = JsonNewsRepository(tmp_path / "news.json")

    repository.save_all([{"id": 1}, {"id": 2}, {"id": 3}], limit=2)

    assert repository.load_all() == [{"id": 2}, {"id": 3}]


def test_postgres_news_repository_loads_news():
    client = FakeClient(rows=[
        ("news-id", "author@example.com", "Author", "Title", "Body", "Source", "Berlin", [], "2026-01-01")
    ])
    repository = PostgresNewsRepository(client=client)

    data = repository.load_all()

    assert data[0]["author_email"] == "author@example.com"
    assert data[0]["title"] == "Title"


def test_postgres_news_repository_saves_news():
    client = FakeClient()
    repository = PostgresNewsRepository(client=client)

    repository.save_all([{"title": "Title", "body": "Body", "author_email": "author@example.com"}])

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM news_items"
    assert "INSERT INTO news_items" in client.cursor.calls[1][0]


def test_json_user_ai_settings_repository_prefers_new_settings(tmp_path):
    repository = JsonUserAiSettingsRepository(tmp_path / "settings.json", tmp_path / "legacy.json")
    repository.settings_store.save({"alice@example.com": {"ai_recommendations": True}})
    repository.legacy_privacy_store.save({"alice@example.com": {"ai_recommendations": False}})

    assert repository.load_for_email("ALICE@example.com") == {"ai_recommendations": True}


def test_postgres_user_ai_settings_repository_loads_settings():
    client = FakeClient(rows=[({"ai_recommendations": True},)])
    repository = PostgresUserAiSettingsRepository(client=client)

    assert repository.load_for_email("alice@example.com") == {"ai_recommendations": True}


def test_postgres_user_ai_settings_repository_saves_settings():
    client = FakeClient()
    repository = PostgresUserAiSettingsRepository(client=client)

    repository.save_for_email("ALICE@example.com", {"private_profile": True})

    assert client.connection.committed is True
    assert "INSERT INTO user_ai_settings" in client.cursor.calls[0][0]
    assert client.cursor.calls[0][1]["email"] == "alice@example.com"


def test_factories_use_postgres():
    settings = DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db")

    assert isinstance(get_news_repository(settings=settings, client=FakeClient()), PostgresNewsRepository)
    assert isinstance(get_user_ai_settings_repository(settings=settings, client=FakeClient()), PostgresUserAiSettingsRepository)
