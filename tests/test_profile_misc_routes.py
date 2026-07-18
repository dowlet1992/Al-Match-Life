import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email, name):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def test_blocked_users_page_lists_blocked_profiles(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_blocked_users", lambda email: ["bob@example.com"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/blocked/alice@example.com")

    assert response.status_code == 200
    assert "Заблокированные".encode("utf-8") in response.data
    assert b"Bob" in response.data
    assert b"/unblock_user/alice@example.com/bob@example.com" in response.data


def test_blocked_users_page_empty_state(monkeypatch):
    alice = make_user("alice@example.com", "Alice")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_blocked_users", lambda email: [])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/blocked/alice@example.com")

    assert response.status_code == 200
    assert "Чёрный список пуст.".encode("utf-8") in response.data


def test_hashtag_page_lists_matching_posts(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: {
        "posts": [
            {"email": "bob@example.com", "hashtags": ["ai"], "text": "AI idea", "date": "2026-07-18"},
            {"email": "bob@example.com", "hashtags": ["travel"], "text": "Other", "date": "2026-07-18"},
        ]
    })

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/hashtag/alice@example.com/ai")

    assert response.status_code == 200
    assert b"AI idea" in response.data
    assert b"Other" not in response.data
    assert b"Bob" in response.data


def test_hashtag_page_empty_state(monkeypatch):
    alice = make_user("alice@example.com", "Alice")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/hashtag/alice@example.com/ai")

    assert response.status_code == 200
    assert "По хэштегу #ai пока нет публикаций.".encode("utf-8") in response.data
