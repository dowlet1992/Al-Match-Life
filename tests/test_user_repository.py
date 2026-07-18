from backend.database import DatabaseSettings
from backend.models import User
from backend.repositories.user_repository import (
    JsonUserRepository,
    PostgresUserRepository,
    get_user_repository,
    user_from_record,
    user_to_database_params,
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


def make_user(email="alice@example.com"):
    return User(
        "Alice",
        30,
        email,
        "hashed-password",
        "Germany",
        "Bio",
        "Engineer",
        "Partners",
        ["English"],
        ["Build"],
        ["AI"],
        ["Python"],
    )


def test_user_from_record_accepts_database_tuple():
    row = (
        "Alice", 30, "alice@example.com", "hashed", "Germany", "Bio",
        "Engineer", "Partners", ["English"], ["Build"], ["AI"], ["Python"],
        70, True, True, "2026-01-01", True, False, True, "2026-01-02", "email",
    )

    user = user_from_record(row)

    assert user.email == "alice@example.com"
    assert user.password == "hashed"
    assert user.account_verified_via == "email"


def test_user_to_database_params_normalizes_email():
    params = user_to_database_params(make_user("ALICE@example.com"))

    assert params["email"] == "alice@example.com"
    assert params["password_hash"] == "hashed-password"
    assert params["languages"] == ["English"]


def test_json_user_repository_round_trip(tmp_path):
    repository = JsonUserRepository(tmp_path / "users.json")

    repository.save_all([make_user()])
    users = repository.load_all()

    assert len(users) == 1
    assert users[0].email == "alice@example.com"


def test_postgres_user_repository_loads_users():
    client = FakeClient(rows=[(
        "Alice", 30, "alice@example.com", "hashed", "Germany", "Bio",
        "Engineer", "Partners", [], [], [], [], 50, False, False,
        "2026-01-01", False, False, True, None, "",
    )])
    repository = PostgresUserRepository(client=client)

    users = repository.load_all()

    assert len(users) == 1
    assert users[0].email == "alice@example.com"
    assert "FROM users" in client.cursor.calls[0][0]


def test_postgres_user_repository_saves_users_with_upsert():
    client = FakeClient()
    repository = PostgresUserRepository(client=client)

    repository.save_all([make_user()])

    assert client.connection.committed is True
    query, params = client.cursor.calls[0]
    assert "ON CONFLICT (email) DO UPDATE" in query
    assert params["email"] == "alice@example.com"


def test_get_user_repository_uses_postgres_for_default_users_file():
    repository = get_user_repository(settings=DatabaseSettings(
        storage_backend="postgres",
        database_url="postgresql://user:pass@example.com/db",
    ), client=FakeClient())

    assert isinstance(repository, PostgresUserRepository)


def test_get_user_repository_uses_json_for_explicit_filename(tmp_path):
    repository = get_user_repository(
        filename=tmp_path / "users.json",
        settings=DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db"),
        client=FakeClient(),
    )

    assert isinstance(repository, JsonUserRepository)
