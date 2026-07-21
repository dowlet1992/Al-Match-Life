import app
from backend.models import User


def test_settings_page_uses_clean_professional_headings(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "show_in_search": True,
        "private_profile": False,
        "message_permission": "everyone",
        "ai_recommendations": True,
        "ai_life_radar": True,
        "recommend_my_profile": True,
        "ai_activity_analysis": True,
        "notifications_enabled": True,
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"

    response = client.get("/settings/alice@example.com", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"<h1>Settings</h1>" in response.data
    assert b"Account center" in response.data
    assert b'id="settingsSearch"' in response.data
    assert b"Search settings" in response.data
    assert b"<h2>Privacy</h2>" in response.data
    assert b"<h2>Notifications</h2>" in response.data
    assert b' name="auto_translate_messages"' in response.data
    assert b' name="message_translation_language"' in response.data
    assert b' name="live_call_captions"' in response.data
    assert b' name="allow_server_call_transcription"' in response.data
    assert b' name="auto_translate_call_captions"' in response.data
    assert b' name="call_caption_language"' in response.data
    assert b' name="call_spoken_language"' in response.data
    assert "⚙️".encode("utf-8") not in response.data


def test_settings_page_uses_phone_language_from_accept_language(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "show_in_search": True,
        "private_profile": False,
        "message_permission": "everyone",
        "ai_recommendations": True,
        "ai_life_radar": True,
        "recommend_my_profile": True,
        "ai_activity_analysis": True,
        "notifications_enabled": True,
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/settings/alice@example.com", headers={"Accept-Language": "de-DE"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert b"<h1>Einstellungen</h1>" in response.data
    assert b"<h2>Privatsph" in response.data


def test_settings_page_keeps_new_sections_in_selected_language(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["language"] = "tr"

    response = client.get("/settings/alice@example.com")

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Hesap".encode("utf-8") in response.data
    assert "Hesap merkezi".encode("utf-8") in response.data
    assert "Ayarlarda ara".encode("utf-8") in response.data
    assert "Güvenlik".encode("utf-8") in response.data
    assert "Arayüz dili".encode("utf-8") in response.data
    assert "Аккаунт".encode("utf-8") not in response.data
    assert "Безопасность".encode("utf-8") not in response.data
    assert "Центр аккаунта".encode("utf-8") not in response.data
    assert b"{{ ui." not in response.data


def test_settings_update_persists_extended_controls(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    saved_settings = {}
    saved_users = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_user_ai_settings", lambda email, settings: saved_settings.update(settings))
    monkeypatch.setattr(app, "save_users_to_json", lambda users: saved_users.append(users))

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"

    response = client.post(
        "/settings/alice@example.com/privacy_ai",
        data={
            "csrf_token": "token-1",
            "language": "tr",
            "profile_visibility": "friends",
            "story_visibility": "close_friends",
            "message_permission": "verified",
            "ai_personalization_level": "high",
            "show_in_search": "on",
            "show_online_status": "on",
            "ai_memory_enabled": "on",
            "ai_feed_learning": "on",
            "message_notifications": "on",
            "login_alerts": "on",
            "sensitive_content_filter": "on",
            "auto_translate_messages": "on",
            "message_translation_language": "en",
            "live_call_captions": "on",
            "allow_server_call_transcription": "on",
            "auto_translate_call_captions": "on",
            "call_caption_language": "en",
        },
    )

    assert response.status_code == 302
    assert user.language == "tr"
    assert saved_users
    assert saved_settings["profile_visibility"] == "friends"
    assert saved_settings["story_visibility"] == "close_friends"
    assert saved_settings["message_permission"] == "verified"
    assert saved_settings["ai_personalization_level"] == "high"
    assert saved_settings["show_online_status"] is True
    assert saved_settings["ai_memory_enabled"] is True
    assert saved_settings["two_factor_required"] is False
    assert saved_settings["auto_translate_messages"] is True
    assert saved_settings["message_translation_language"] == "en"
    assert saved_settings["live_call_captions"] is True
    assert saved_settings["allow_server_call_transcription"] is True
    assert saved_settings["auto_translate_call_captions"] is True
    assert saved_settings["call_caption_language"] == "en"
