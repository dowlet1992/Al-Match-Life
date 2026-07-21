import app
from backend.database import DatabaseSettings
from backend.models import User
from backend.repositories.device_push_repository import JsonDevicePushRepository, PostgresDevicePushRepository, get_device_push_repository
from backend.services import device_push_service


VALID_TOKEN = "push-token-" + ("a" * 40)
VALID_DEVICE_ID = "device-1234567890abcdef"


class FakeCursor:
    def __init__(self, rows=None, row=None):
        self.rows, self.row, self.calls, self.rowcount = rows or [], row, [], 1
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, query, params=None): self.calls.append((query, params))
    def fetchall(self): return self.rows
    def fetchone(self): return self.row


class FakeConnection:
    def __init__(self, cursor): self.cursor_value, self.committed = cursor, False
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.cursor_value
    def commit(self): self.committed = True


class FakeClient:
    def __init__(self, rows=None, row=None):
        self.cursor = FakeCursor(rows, row)
        self.connection = FakeConnection(self.cursor)
    def connect(self): return self.connection


def registration():
    value, error = device_push_service.normalize_registration({
        "platform": "ios", "device_id": VALID_DEVICE_ID, "token": VALID_TOKEN,
        "app_version": "2.1.0", "locale": "de-DE",
    })
    assert error is None
    return value


def test_push_registration_validation_and_public_projection():
    value = registration()
    assert len(value["token_hash"]) == 64
    assert "token" not in device_push_service.public_device(value)
    assert device_push_service.normalize_registration({"platform": "desktop"})[1]


def test_json_push_device_lifecycle_and_token_transfer(tmp_path):
    repository = JsonDevicePushRepository(tmp_path / "push.json")
    repository.upsert("alice@example.com", registration())
    repository.upsert("bob@example.com", {**registration(), "device_id": "other-1234567890abcdef"})
    assert repository.list_for_user("alice@example.com") == []
    assert len(repository.list_for_user("bob@example.com")) == 1
    assert repository.revoke("bob@example.com", "other-1234567890abcdef") is True
    assert repository.revoke("bob@example.com", "other-1234567890abcdef") is False


def test_postgres_push_upsert_transfers_token_and_commits():
    row = (VALID_DEVICE_ID, "ios", "2.1.0", "de-de", "2026-01-01")
    client = FakeClient(row=row)
    device = PostgresDevicePushRepository(client).upsert("alice@example.com", registration())
    assert "DELETE FROM push_devices WHERE token_hash" in client.cursor.calls[0][0]
    assert "ON CONFLICT (user_id, device_id) DO UPDATE" in client.cursor.calls[1][0]
    assert device["device_id"] == VALID_DEVICE_ID
    assert client.connection.committed is True


def test_push_repository_factory_selects_postgres():
    settings = DatabaseSettings("postgres", "postgresql://example/db")
    assert isinstance(get_device_push_repository(settings, FakeClient()), PostgresDevicePushRepository)


def test_push_device_api_requires_authentication():
    assert app.app.test_client().get("/api/push/devices").status_code == 401


def test_push_device_api_registers_lists_and_revokes_without_exposing_token(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hash", "DE", "", "", "", [], [], [], [])
    repository = JsonDevicePushRepository("ignored.json")
    stored = []
    monkeypatch.setattr(repository, "upsert", lambda email, value: stored.append((email, value)) or value)
    monkeypatch.setattr(repository, "list_for_user", lambda email: [stored[0][1]] if stored else [])
    monkeypatch.setattr(repository, "revoke", lambda email, device_id: True)
    monkeypatch.setattr(app, "get_device_push_repository", lambda: repository)
    monkeypatch.setattr(app, "get_api_current_user", lambda: user)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "push-csrf-token"
    response = client.post("/api/push/devices", json={"platform": "web", "device_id": VALID_DEVICE_ID, "token": VALID_TOKEN}, headers={"X-CSRF-Token": "push-csrf-token"})
    listed = client.get("/api/push/devices")
    revoked = client.delete(f"/api/push/devices/{VALID_DEVICE_ID}", headers={"X-CSRF-Token": "push-csrf-token"})
    assert response.status_code == 201
    assert "token" not in response.get_json()["device"]
    assert "token" not in listed.get_json()["devices"][0]
    assert revoked.get_json()["revoked"] is True


def test_push_device_migration_has_constraints_and_active_index():
    schema = open("database/migrations/003_push_devices.sql", encoding="utf-8").read()
    assert "REFERENCES users(id) ON DELETE CASCADE" in schema
    assert "token_hash TEXT NOT NULL UNIQUE" in schema
    assert "WHERE revoked_at IS NULL" in schema


def test_call_push_outbox_migration_is_idempotent_and_retry_ready():
    schema = open("database/migrations/004_call_push_outbox.sql", encoding="utf-8").read()
    assert "event_id TEXT PRIMARY KEY" in schema
    assert "attempts INTEGER NOT NULL DEFAULT 0" in schema
    assert "expires_at TIMESTAMPTZ NOT NULL" in schema
    assert "WHERE status = 'pending'" in schema


def test_per_device_push_delivery_migration_has_durable_receipts():
    schema = open("database/migrations/005_call_push_deliveries.sql", encoding="utf-8").read()
    assert "PRIMARY KEY (event_id, device_id)" in schema
    assert "REFERENCES call_push_outbox(event_id) ON DELETE CASCADE" in schema
    assert "attempts INTEGER NOT NULL DEFAULT 0" in schema
    assert "WHERE status = 'pending'" in schema


def test_push_config_returns_only_public_vapid_material(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hash", "DE", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "get_api_current_user", lambda: user)
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "public-base64url-key")
    response = app.app.test_client().get("/api/push/config")
    assert response.status_code == 200
    assert response.get_json()["web_push"] == {"configured": True, "public_key": "public-base64url-key"}
    assert response.headers["Cache-Control"] == "private, no-store"


def test_cookie_push_registration_requires_csrf(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hash", "DE", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "get_api_current_user", lambda: user)
    response = app.app.test_client().post("/api/push/devices", json={
        "platform": "web", "device_id": VALID_DEVICE_ID, "token": VALID_TOKEN,
    })
    assert response.status_code == 403


def test_push_service_worker_has_root_scope_security_headers():
    response = app.app.test_client().get("/push-service-worker.js")
    assert response.status_code == 200
    assert response.headers["Service-Worker-Allowed"] == "/"
    assert response.headers["Cache-Control"] == "no-cache"
    script = response.get_data(as_text=True)
    assert "showNotification" in script
    assert "clients.openWindow" in script
    assert "safeEmail" in script
