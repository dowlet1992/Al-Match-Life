from backend.database import DatabaseSettings
from backend.repositories.feed_repository import (
    JsonFeedRepository,
    PostgresFeedRepository,
    get_feed_repository,
    normalize_feed_data,
    normalize_post,
)


class FakeCursor:
    def __init__(self, result_sets=None):
        self.result_sets = list(result_sets or [])
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        if self.result_sets:
            return self.result_sets.pop(0)
        return []


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
    def __init__(self, result_sets=None):
        self.cursor = FakeCursor(result_sets)
        self.connection = FakeConnection(self.cursor)

    def connect(self):
        return self.connection


def test_normalize_feed_data_requires_posts_list():
    assert normalize_feed_data({"posts": {}}) == {"posts": []}
    assert normalize_feed_data([]) == {"posts": []}


def test_normalize_post_sets_expected_lists():
    post = normalize_post({"id": 1, "text": "Hello", "likes": "bad"})

    assert post["likes"] == []
    assert post["comments"] == []
    assert post["type"] == "Идея"


def test_json_feed_repository_round_trip(tmp_path):
    repository = JsonFeedRepository(tmp_path / "feed.json")
    data = {"posts": [{"id": 1, "text": "Hello"}]}

    repository.save_all(data)

    assert repository.load_all() == data


def test_postgres_feed_repository_loads_feed_with_interactions():
    client = FakeClient(result_sets=[
        [(1, "alice@example.com", "Alice", "Идея", "Hello", "en", "Berlin", ["ai"], [], "2026-01-01")],
        [(1, "bob@example.com")],
        [(1, "carol@example.com")],
        [(1, "bob@example.com", "Bob", "Nice", "2026-01-02")],
    ])
    repository = PostgresFeedRepository(client=client)

    feed = repository.load_all()

    post = feed["posts"][0]
    assert post["email"] == "alice@example.com"
    assert post["likes"] == ["bob@example.com"]
    assert post["saves"] == ["carol@example.com"]
    assert post["comments"][0]["text"] == "Nice"
    assert len(client.cursor.calls) == 4


def test_postgres_feed_repository_saves_feed_with_interactions():
    client = FakeClient()
    repository = PostgresFeedRepository(client=client)

    repository.save_all({
        "posts": [{
            "id": 1,
            "email": "alice@example.com",
            "type": "Идея",
            "text": "Hello",
            "likes": ["bob@example.com"],
            "saves": ["carol@example.com"],
            "comments": [{"author": "bob@example.com", "text": "Nice"}],
        }]
    })

    assert client.connection.committed is True
    queries = [query for query, _params in client.cursor.calls]
    assert queries[0] == "DELETE FROM feed_post_comments"
    assert queries[1] == "DELETE FROM feed_post_saves"
    assert queries[2] == "DELETE FROM feed_post_likes"
    assert queries[3] == "DELETE FROM feed_posts"
    assert any("INSERT INTO feed_posts" in query for query in queries)
    assert any("INSERT INTO feed_post_likes" in query for query in queries)
    assert any("INSERT INTO feed_post_saves" in query for query in queries)
    assert any("INSERT INTO feed_post_comments" in query for query in queries)


def test_get_feed_repository_uses_postgres_for_default_feed_file():
    repository = get_feed_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://user:pass@example.com/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresFeedRepository)


def test_get_feed_repository_uses_json_for_explicit_filename(tmp_path):
    repository = get_feed_repository(
        filename=tmp_path / "feed.json",
        settings=DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db"),
        client=FakeClient(),
    )

    assert isinstance(repository, JsonFeedRepository)
