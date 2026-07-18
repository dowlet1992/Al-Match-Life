from backend.database import DatabaseSettings
from backend.repositories.proof_repository import (
    JsonProofRepository,
    PostgresProofRepository,
    get_proof_repository,
    proof_database_id,
)
from backend.repositories.stories_repository import (
    JsonStoriesRepository,
    PostgresStoriesRepository,
    get_stories_repository,
    story_database_id,
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


def test_story_database_id_is_stable_for_legacy_numeric_id():
    story = {"id": 1, "email": "alice@example.com", "media_url": "/story.jpg"}

    assert story_database_id(story) == story_database_id(story)
    assert story_database_id(story) != "1"


def test_json_stories_repository_round_trip(tmp_path):
    repository = JsonStoriesRepository(tmp_path / "stories.json")
    data = {"stories": [{"id": 1, "email": "alice@example.com"}]}

    repository.save_all(data)

    assert repository.load_all() == data


def test_postgres_stories_repository_loads_stories():
    client = FakeClient(rows=[
        ("story-id", "alice@example.com", "Alice", "/story.jpg", "image", "Hello", "2026-01-01")
    ])
    repository = PostgresStoriesRepository(client=client)

    data = repository.load_all()

    assert data["stories"][0]["email"] == "alice@example.com"
    assert data["stories"][0]["media_url"] == "/story.jpg"


def test_postgres_stories_repository_saves_stories():
    client = FakeClient()
    repository = PostgresStoriesRepository(client=client)

    repository.save_all({"stories": [{"id": 1, "email": "alice@example.com", "media_url": "/story.jpg"}]})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM stories"
    assert "INSERT INTO stories" in client.cursor.calls[1][0]


def test_get_stories_repository_uses_postgres_for_default_file():
    repository = get_stories_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://example/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresStoriesRepository)


def test_proof_database_id_is_stable_for_legacy_numeric_id():
    proof = {"id": 1, "email": "alice@example.com", "title": "Certificate"}

    assert proof_database_id(proof) == proof_database_id(proof)
    assert proof_database_id(proof) != "1"


def test_json_proof_repository_round_trip(tmp_path):
    repository = JsonProofRepository(tmp_path / "proofs.json")
    data = {"proofs": [{"id": 1, "email": "alice@example.com"}]}

    repository.save_all(data)

    assert repository.load_all() == data


def test_postgres_proof_repository_loads_proofs():
    client = FakeClient(rows=[
        ("proof-id", "alice@example.com", "skill", "Certificate", "Desc", "/proof.jpg", "new", "AI summary", "2026-01-01")
    ])
    repository = PostgresProofRepository(client=client)

    data = repository.load_all()

    assert data["proofs"][0]["email"] == "alice@example.com"
    assert data["proofs"][0]["title"] == "Certificate"


def test_postgres_proof_repository_saves_proofs():
    client = FakeClient()
    repository = PostgresProofRepository(client=client)

    repository.save_all({"proofs": [{"id": 1, "email": "alice@example.com", "title": "Certificate"}]})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM proof_items"
    assert "INSERT INTO proof_items" in client.cursor.calls[1][0]


def test_get_proof_repository_uses_postgres_for_default_file():
    repository = get_proof_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://example/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresProofRepository)
