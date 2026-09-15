import app
from backend.models import User


def test_privacy_page_uses_saved_german_language(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], [], [], [])
    alice.language = "de"

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_user_privacy", lambda email: {
        "receive_recommendations": True,
        "show_me_to_others": True,
        "show_in_search": True,
        "allow_messages": True,
        "verified_only_messages": False,
        "vip_mode": False,
    })

    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = alice.email
        session_data["session_version"] = 1

    response = client.get("/privacy/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["settings"].encode() in response.data
    assert "Управляйте".encode("utf-8") not in response.data
    assert "Получать рекомендации".encode("utf-8") not in response.data
