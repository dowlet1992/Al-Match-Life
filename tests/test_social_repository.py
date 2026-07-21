from backend.database import DatabaseSettings
from backend.repositories.social_repository import (
    JsonSocialRepository,
    PostgresSocialRepository,
    get_social_repository,
    normalize_social_data,
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

    def fetchone(self):
        if not self.result_sets:
            return None
        rows = self.result_sets.pop(0)
        return rows[0] if rows else None


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


def test_normalize_social_data_requires_lists():
    data = normalize_social_data({"friends": {}, "follows": [], "friend_requests": "bad"})

    assert data == {"friends": [], "follows": [], "friend_requests": []}


def test_json_social_repository_round_trip(tmp_path):
    repository = JsonSocialRepository(tmp_path / "social.json")
    data = {
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}],
        "friend_requests": [],
    }

    repository.save_all(data)

    assert repository.load_all() == data


def test_json_follow_mutations_are_idempotent_and_do_not_lose_concurrent_edges(tmp_path):
    repository = JsonSocialRepository(tmp_path / "social.json")
    targets = [f"person{index}@example.com" for index in range(20)]

    with ThreadPoolExecutor(max_workers=8) as executor:
        changed = list(executor.map(lambda target: repository.add_follow("alice@example.com", target), targets))

    assert all(changed)
    assert repository.add_follow("ALICE@example.com", targets[0].upper()) is False
    assert len(repository.load_all()["follows"]) == len(targets)
    assert repository.remove_follow("alice@example.com", targets[0]) is True
    assert repository.remove_follow("alice@example.com", targets[0]) is False
    assert len(repository.load_all()["follows"]) == len(targets) - 1


def test_postgres_social_repository_loads_all_relationships():
    client = FakeClient(result_sets=[
        [("alice@example.com", "bob@example.com")],
        [("alice@example.com", "carol@example.com")],
        [("bob@example.com", "alice@example.com")],
    ])
    repository = PostgresSocialRepository(client=client)

    data = repository.load_all()

    assert data["follows"] == [{"follower": "alice@example.com", "following": "bob@example.com"}]
    assert data["friends"] == [{"user": "alice@example.com", "friend": "carol@example.com"}]
    assert data["friend_requests"] == [{"from": "bob@example.com", "to": "alice@example.com"}]
    assert len(client.cursor.calls) == 3


def test_postgres_social_repository_saves_all_relationships():
    client = FakeClient()
    repository = PostgresSocialRepository(client=client)

    repository.save_all({
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}],
        "friend_requests": [{"from": "bob@example.com", "to": "alice@example.com"}],
    })

    assert client.connection.committed is True
    queries = [query for query, _params in client.cursor.calls]
    assert queries[0] == "DELETE FROM friend_requests WHERE status = 'pending'"
    assert queries[1] == "DELETE FROM friendships"
    assert queries[2] == "DELETE FROM social_follows"
    assert any("INSERT INTO social_follows" in query for query in queries)
    assert any("INSERT INTO friendships" in query for query in queries)
    assert any("INSERT INTO friend_requests" in query for query in queries)


def test_postgres_follow_mutations_are_targeted_and_report_change():
    add_client = FakeClient(result_sets=[[(1,)]])
    add_repository = PostgresSocialRepository(client=add_client)
    assert add_repository.add_follow("ALICE@example.com", "BOB@example.com") is True
    add_query, add_params = add_client.cursor.calls[0]
    assert "INSERT INTO social_follows" in add_query
    assert "ON CONFLICT DO NOTHING" in add_query
    assert "DELETE FROM social_follows" not in add_query
    assert add_params == {"follower": "alice@example.com", "following": "bob@example.com"}
    assert add_client.connection.committed is True

    remove_client = FakeClient(result_sets=[[]])
    remove_repository = PostgresSocialRepository(client=remove_client)
    assert remove_repository.remove_follow("alice@example.com", "bob@example.com") is False
    remove_query, remove_params = remove_client.cursor.calls[0]
    assert "DELETE FROM social_follows" in remove_query
    assert "RETURNING 1" in remove_query
    assert remove_params == {"follower": "alice@example.com", "following": "bob@example.com"}


def test_get_social_repository_uses_postgres_for_default_social_file():
    repository = get_social_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://user:pass@example.com/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresSocialRepository)


def test_get_social_repository_uses_json_for_explicit_filename(tmp_path):
    repository = get_social_repository(
        filename=tmp_path / "social.json",
        settings=DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db"),
        client=FakeClient(),
    )

    assert isinstance(repository, JsonSocialRepository)
from concurrent.futures import ThreadPoolExecutor
