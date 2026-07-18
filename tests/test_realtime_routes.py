import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def test_typing_route_saves_sender_receiver_key(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    typing_store = {}
    saved = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_typing_status", lambda: typing_store)
    monkeypatch.setattr(app, "save_typing_status", lambda data: saved.append(data.copy()))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/typing/alice@example.com/bob@example.com", data={"csrf_token": "token-1"})

    assert response.status_code == 200
    assert response.data == b"OK"
    assert "alice@example.com->bob@example.com" in typing_store
    assert saved


def test_presence_route_saves_timestamp(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    presence_store = {}
    saved = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_presence_status", lambda: presence_store)
    monkeypatch.setattr(app, "save_presence_status", lambda data: saved.append(data.copy()))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/presence/alice@example.com", data={"csrf_token": "token-1"})

    assert response.status_code == 200
    assert response.data == b"OK"
    assert "alice@example.com" in presence_store
    assert saved


def test_realtime_routes_reject_missing_csrf(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/presence/alice@example.com")

    assert response.status_code == 403
