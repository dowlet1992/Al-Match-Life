import app
import pytest
from backend.models import User
from backend.i18n import UI_LANGUAGES


def make_user(language="ru"):
    user = User(
        "Alice", 28, "alice@example.com", "hashed", "Germany",
        "", "", "", [], [], [], [],
    )
    user.language = language
    return user


def authenticated_client(user, language=None):
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = user.email
        session["csrf_token"] = "language-token"
        if language:
            session["language"] = language
    return client


def test_language_setting_updates_profile_and_session_immediately(monkeypatch):
    user = make_user("ru")
    saved = []
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {})
    monkeypatch.setattr(app, "save_user_raw_settings", lambda email, settings: saved.append((email, settings)))
    client = authenticated_client(user, "ru")

    response = client.post(
        f"/set_language/{user.id}/de",
        headers={
            "X-CSRF-Token": "language-token",
            "X-Requested-With": "fetch",
            "Accept": "application/json",
            "Referer": f"http://localhost/settings/{user.id}",
        },
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "language": "de",
        "redirect": f"/settings/{user.id}",
    }
    assert user.language == "de"
    assert saved == [(user.email, {"interface_language": "de"})]
    with client.session_transaction() as session:
        assert session["language"] == "de"


def test_saved_interface_language_is_used_after_session_is_cleared(monkeypatch):
    user = make_user("ru")
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"interface_language": "en"})
    client = authenticated_client(user)

    response = client.get(f"/settings/{user.id}")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b">Settings<" in response.data


def test_saved_interface_language_overrides_stale_session(monkeypatch):
    user = make_user("ru")
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"interface_language": "en"})
    client = authenticated_client(user, "ru")

    response = client.get(f"/settings/{user.id}")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data


def test_saved_supported_language_is_used_consistently(monkeypatch):
    user = make_user("tr")
    monkeypatch.setattr(app, "users", [user])
    client = authenticated_client(user, "tr")

    response = client.get(f"/settings/{user.id}")

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Ayarlar".encode() in response.data
    assert response.headers["Cache-Control"] == "no-store, private"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Vary"] == "Cookie, Accept-Language"
    assert b"settings.js?v=20260816-language-sync-2" in response.data


def test_core_pages_share_selected_interface_language(monkeypatch):
    user = make_user("de")
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    client = authenticated_client(user, "de")

    routes = (
        f"/dashboard/{user.id}",
        f"/profile/{user.id}",
        f"/ai_copilot/{user.id}",
        f"/radar/{user.id}",
        f"/messages/{user.id}",
        f"/settings/{user.id}",
    )
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200, route
        assert b'<html lang="de" dir="ltr">' in response.data, route
        assert "Einstellungen".encode() in response.data, route


def test_language_endpoint_cannot_change_another_users_preference(monkeypatch):
    alice = make_user("ru")
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob.language = "en"
    monkeypatch.setattr(app, "users", [alice, bob])
    client = authenticated_client(alice, "ru")

    response = client.post(
        f"/set_language/{bob.id}/de",
        headers={"X-CSRF-Token": "language-token"},
    )

    assert response.status_code == 403
    assert bob.language == "en"


@pytest.mark.parametrize("language", tuple(UI_LANGUAGES))
def test_every_supported_interface_language_can_be_selected(monkeypatch, language):
    user = make_user("ru")
    saved = []
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {})
    monkeypatch.setattr(app, "save_user_raw_settings", lambda email, settings: saved.append(settings))
    client = authenticated_client(user, "ru")

    response = client.post(
        f"/set_language/{user.id}/{language}",
        headers={
            "X-CSRF-Token": "language-token",
            "X-Requested-With": "fetch",
            "Accept": "application/json",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["language"] == language
    assert saved == [{"interface_language": language}]


def test_settings_language_selector_lists_full_supported_catalog(monkeypatch):
    user = make_user("en")
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"interface_language": "en"})
    client = authenticated_client(user, "en")

    response = client.get(f"/settings/{user.id}")

    assert response.status_code == 200
    for language, display_name in UI_LANGUAGES.items():
        assert f'<option value="{language}"'.encode() in response.data
        assert display_name.encode() in response.data
