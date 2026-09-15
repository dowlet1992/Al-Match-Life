import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email


def test_notifications_page_renders_empty_state(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "mark_notifications_read", lambda email: None)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/notifications/alice@example.com")

    assert response.status_code == 200
    assert "Уведомлений пока нет".encode("utf-8") in response.data


def test_notifications_page_uses_saved_turkish_language(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    alice.language = "tr"
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "mark_notifications_read", lambda email: None)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/notifications/{alice.id}", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Henüz bildirim yok".encode() in response.data
    assert "Yeni takipçiler, arkadaşlık istekleri ve yorumlar burada görünecek.".encode() in response.data
    assert b"No notifications yet" not in response.data


def test_notifications_accept_uuid_and_reject_another_users_uuid(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "France", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "mark_notifications_read", lambda email: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    own_response = client.get(f"/notifications/{alice.id}")
    other_response = client.get(f"/notifications/{bob.id}")

    assert own_response.status_code == 200
    assert other_response.status_code == 403


def test_notifications_page_renders_friend_request_actions(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "France", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    marked = []
    monkeypatch.setattr(app, "mark_notifications_read", lambda email: marked.append(email))
    monkeypatch.setattr(
        app,
        "get_notifications",
        lambda email: [
            {
                "type": "friend_request",
                "text": "Bob sent you a friend request.",
                "from_email": "bob@example.com",
                "time_label": "10:20",
                "status": "pending",
            }
        ],
    )

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/notifications/alice@example.com")

    assert response.status_code == 200
    assert b"Bob sent you a friend request." in response.data
    assert f"/profile/{bob.id}".encode() in response.data
    assert b"/profile/bob@example.com" not in response.data
    assert f"/accept_friend_request/{alice.id}/{bob.id}".encode() in response.data
    assert f"/decline_friend_request/{alice.id}/{bob.id}".encode() in response.data
    assert f"/friend_requests/{alice.id}".encode() in response.data
    assert b"notification-card unread" in response.data
    assert marked == [alice.email]
