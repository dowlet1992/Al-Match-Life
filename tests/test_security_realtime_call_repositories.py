from backend.database import DatabaseSettings
from backend.repositories.call_signal_repository import JsonCallSignalRepository, PostgresCallSignalRepository, get_call_signal_repository
from backend.repositories.realtime_repository import JsonRealtimeRepository, PostgresRealtimeRepository, get_realtime_repository
from backend.repositories.security_repository import JsonSecurityRepository, PostgresSecurityRepository, get_security_repository, split_attempt_key


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


def test_split_attempt_key():
    assert split_attempt_key("user@example.com::127.0.0.1") == ("user@example.com", "127.0.0.1")
    assert split_attempt_key("bad") == ("bad", "")


def test_json_security_repository_round_trip(tmp_path):
    repository = JsonSecurityRepository(tmp_path / "attempts.json", tmp_path / "events.json")
    repository.save_login_attempts({"key": {"attempts": []}})
    repository.save_security_events([{"event": "login"}])

    assert repository.load_login_attempts() == {"key": {"attempts": []}}
    assert repository.load_security_events() == [{"event": "login"}]


def test_postgres_security_repository_saves_events():
    client = FakeClient()
    repository = PostgresSecurityRepository(client=client)

    repository.save_security_events([{"event": "login", "email": "a@test.com"}])

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM security_events"
    assert "INSERT INTO security_events" in client.cursor.calls[1][0]


def test_postgres_realtime_repository_saves_presence_and_typing():
    client = FakeClient()
    repository = PostgresRealtimeRepository(client=client)

    repository.save_typing_status({"alice@example.com::bob@example.com": {"is_typing": True}})
    repository.save_presence_status({"alice@example.com": {"online": True}})

    assert client.connection.committed is True
    assert any("INSERT INTO realtime_typing" in query for query, _ in client.cursor.calls)
    assert any("INSERT INTO realtime_presence" in query for query, _ in client.cursor.calls)


def test_json_realtime_repository_round_trip(tmp_path):
    repository = JsonRealtimeRepository(tmp_path / "typing.json", tmp_path / "presence.json")
    repository.save_typing_status({"a::b": True})
    repository.save_presence_status({"a": {"online": True}})

    assert repository.load_typing_status() == {"a::b": True}
    assert repository.load_presence_status() == {"a": {"online": True}}


def test_postgres_call_signal_repository_saves_calls():
    client = FakeClient()
    repository = PostgresCallSignalRepository(client=client)

    repository.save_all({"room": {"type": "offer"}})

    assert client.connection.committed is True
    assert client.cursor.calls[0][0] == "DELETE FROM call_signals"
    assert "INSERT INTO call_signals" in client.cursor.calls[1][0]


def test_json_call_signal_repository_round_trip(tmp_path):
    repository = JsonCallSignalRepository(tmp_path / "calls.json")
    repository.save_all({"room": {"type": "offer"}})

    assert repository.load_all() == {"room": {"type": "offer"}}


def test_repository_factories_use_postgres():
    settings = DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db")

    assert isinstance(get_security_repository(settings=settings, client=FakeClient()), PostgresSecurityRepository)
    assert isinstance(get_realtime_repository(settings=settings, client=FakeClient()), PostgresRealtimeRepository)
    assert isinstance(get_call_signal_repository(settings=settings, client=FakeClient()), PostgresCallSignalRepository)
