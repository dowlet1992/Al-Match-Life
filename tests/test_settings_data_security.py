import json

import app
from backend.models import User


def test_security_activity_page_lists_user_events(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "load_security_events", lambda: [
        {
            "time": "2026-07-16 10:00:00",
            "event": "login_success",
            "email": "alice@example.com",
            "ip": "127.0.0.1",
            "details": "2FA not required",
        },
        {
            "time": "2026-07-16 10:02:00",
            "event": "login_success",
            "email": "bob@example.com",
            "ip": "127.0.0.2",
            "details": "Other user",
        },
    ])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["language"] = "en"

    response = client.get("/settings/alice@example.com/security_activity")

    assert response.status_code == 200
    assert b"Signed in" in response.data
    assert b"Login" in response.data
    assert b"login_success" not in response.data
    assert b"127.0.0.1" in response.data
    assert b"127.0.0.2" not in response.data


def test_data_export_returns_only_current_user_data(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "Bio", "Founder", "Partners", ["English"], ["Build"], ["AI"], ["Sales"])
    other = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user, other])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"profile_visibility": "public"})
    monkeypatch.setattr(app, "get_notifications", lambda email: [{"email": email, "text": "Hello"}])
    monkeypatch.setattr(app, "load_feed", lambda: {
        "posts": [
            {"id": "alice-post", "email": "alice@example.com", "text": "Alice post"},
            {"id": "bob-post", "email": "bob@example.com", "text": "Bob post"},
        ]
    })
    monkeypatch.setattr(app, "load_messages", lambda: [
        {"from": "alice@example.com", "to": "bob@example.com", "text": "Hi Bob"},
        {"from": "bob@example.com", "to": "carol@example.com", "text": "Not Alice"},
    ])
    monkeypatch.setattr(app, "load_security_events", lambda: [
        {"email": "alice@example.com", "event": "login_success"},
        {"email": "bob@example.com", "event": "login_success"},
    ])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/settings/alice@example.com/data_export")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    data = json.loads(response.data.decode("utf-8"))
    assert data["account"]["email"] == "alice@example.com"
    assert "password" not in data["account"]
    assert [post["id"] for post in data["posts"]] == ["alice-post"]
    assert [message["text"] for message in data["messages"]] == ["Hi Bob"]
    assert data["security_events"][0]["email"] == "alice@example.com"


def test_settings_data_routes_reject_other_users(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    other = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user, other])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    assert client.get("/settings/bob@example.com/security_activity").status_code == 403
    assert client.get("/settings/bob@example.com/data_export").status_code == 403
