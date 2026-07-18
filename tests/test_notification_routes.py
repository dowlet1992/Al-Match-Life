import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email


def test_notifications_page_renders_empty_state(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/notifications/alice@example.com")

    assert response.status_code == 200
    assert "Уведомлений пока нет".encode("utf-8") in response.data


def test_notifications_page_renders_friend_request_actions(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "France", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
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
    assert b"/accept_friend_request/alice@example.com/bob@example.com" in response.data
    assert b"/decline_friend_request/alice@example.com/bob@example.com" in response.data
