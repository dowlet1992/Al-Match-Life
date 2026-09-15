import app
from backend.models import User


def test_dashboard_shows_moderation_link_for_admin(monkeypatch):
    admin = User("Admin", 30, "admin@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [admin])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "admin@example.com"

    response = client.get("/dashboard/admin@example.com", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"/admin/moderation/admin@example.com" in response.data
    assert b"Moderation" in response.data


def test_dashboard_navigation_uses_accept_language(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/dashboard/alice@example.com", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b">Profile<" in response.data
    assert b">Messages<" in response.data
    assert b">Settings<" in response.data


def test_dashboard_keeps_composer_in_saved_german_language(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    user.language = "de"

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/dashboard/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["settings"].encode() in response.data
    assert "Опубликовать".encode("utf-8") not in response.data
    assert "Истории".encode("utf-8") not in response.data
    assert "Локация".encode("utf-8") not in response.data
    assert "Новость".encode("utf-8") not in response.data


def test_dashboard_hides_moderation_link_for_regular_user(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/dashboard/alice@example.com")

    assert response.status_code == 200
    assert b"/admin/moderation/" not in response.data
