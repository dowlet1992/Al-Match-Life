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


def test_messages_page_uses_saved_german_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="de")
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
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["messages"].encode() in response.data
    assert app.translation_bundle("de")["settings"].encode() in response.data
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


def test_messages_page_uses_template():
    source = open("backend/messaging_routes.py", encoding="utf-8").read()
    route_start = source.index('def messages_page(identifier):')
    route_source = source[route_start:]

    assert 'render_template(' in route_source
    assert "<!DOCTYPE html>" not in route_source
    assert "dialogs_html" not in route_source


def test_messages_page_rejects_another_users_inbox(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob", language="en")
    monkeypatch.setattr(app, "users", [alice, bob])

    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/messages/{bob.email}")

    assert response.status_code == 403


def test_messages_page_accepts_uuid_and_generates_uuid_chat_links(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob", language="en")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "get_message_permission_status", lambda current, other: (True, "", ""))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/messages/{alice.id}")

    assert response.status_code == 200
    assert f'/chat/{alice.id}/{bob.id}'.encode() in response.data
    assert f'/dashboard/{alice.id}'.encode() in response.data
    assert b'/chat/alice@example.com/bob@example.com' not in response.data


def test_messages_page_escapes_contact_content(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", '<img src=x onerror="alert(1)">')
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "get_message_permission_status", lambda current_user, other_user: (True, "", ""))

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(f"/messages/{alice.email}")

    assert response.status_code == 200
    assert b'<img src=x onerror="alert(1)">' not in response.data
    assert b"&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in response.data
