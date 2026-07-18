import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email, name, language=""):
    user = User(name, 28, email, "hashed", "Germany", "", "Founder", "", [], [], [], [])
    user.language = language
    return user


def test_messages_page_uses_saved_turkish_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="tr")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "get_message_permission_status", lambda current_user, other_user: (True, "", ""))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/messages/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Mesajlar".encode("utf-8") in response.data
    assert "Aktif konuşmalar".encode("utf-8") in response.data
    assert "Yeni konuşma".encode("utf-8") in response.data
    assert "Henüz aktif konuşma yok.".encode("utf-8") in response.data
    assert "Yaz".encode("utf-8") in response.data
    assert "Сообщения".encode("utf-8") not in response.data
    assert "Активные диалоги".encode("utf-8") not in response.data
    assert "Новая переписка".encode("utf-8") not in response.data
    assert "Написать".encode("utf-8") not in response.data


def test_messages_page_renders_existing_dialog_action_in_english(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [{
        "from": "bob@example.com",
        "to": "alice@example.com",
        "message": "Hello Alice",
        "status": "sent",
    }])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "get_message_permission_status", lambda current_user, other_user: (True, "", ""))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/messages/alice@example.com")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"Open chat" in response.data
    assert b"Hello Alice" in response.data
