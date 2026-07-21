from backend.database import DatabaseSettings
from backend.repositories.rate_limit_repository import PostgresRateLimitRepository, get_rate_limit_repository


class FakeCursor:
    def __init__(self, row=(1,)):
        self.row = row
        self.calls = []

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, query, params=None): self.calls.append((query, params))
    def fetchone(self): return self.row


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.committed = False

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.cursor_value
    def commit(self): self.committed = True


class FakeClient:
    def __init__(self, row=(1,)):
        self.cursor = FakeCursor(row)
        self.connection = FakeConnection(self.cursor)

    def connect(self): return self.connection


def test_postgres_rate_limit_uses_atomic_bucket_upsert():
    client = FakeClient(row=(2,))
    repository = PostgresRateLimitRepository(client=client)

    assert repository.allow("hashed-key", "call_signal_poll", 2, 60, 125) is True

    query, params = client.cursor.calls[0]
    assert "DELETE FROM rate_limit_buckets" in query
    assert "ON CONFLICT (key_hash, category, bucket_start) DO UPDATE" in query
    assert "RETURNING request_count" in query
    assert params["key_hash"] == "hashed-key"
    assert params["bucket_start"] == 120
    assert params["expires_epoch"] == 240
    assert client.connection.committed is True


def test_postgres_rate_limit_rejects_count_above_limit():
    repository = PostgresRateLimitRepository(client=FakeClient(row=(3,)))
    assert repository.allow("hashed-key", "call_signal_poll", 2, 60, 125) is False


def test_postgres_rate_limit_cleanup_is_committed():
    client = FakeClient()
    client.cursor.rowcount = 3

    assert PostgresRateLimitRepository(client=client).cleanup_expired() == 3
    assert client.cursor.calls == [("DELETE FROM rate_limit_buckets WHERE expires_at < now()", None)]
    assert client.connection.committed is True


def test_rate_limit_repository_factory_is_postgres_only():
    postgres = DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db")
    json_settings = DatabaseSettings(storage_backend="json")

    assert isinstance(get_rate_limit_repository(settings=postgres, client=FakeClient()), PostgresRateLimitRepository)
    assert get_rate_limit_repository(settings=json_settings) is None
