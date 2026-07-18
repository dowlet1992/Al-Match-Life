import app
from backend.models import User


def _open_onboarding(monkeypatch, accept_language):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "analyze_user_profile", lambda user: {
        "summary": "The more signals you give, the better AI Matches become."
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    return client.get("/onboarding/alice@example.com", headers={"Accept-Language": accept_language})


def test_onboarding_page_uses_english_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "en-US")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"Quick start" in response.data
    assert b"Who do you want to find?" in response.data
    assert b"Show my AI Matches" in response.data
    assert b"Skip for now" in response.data


def test_onboarding_page_uses_german_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "de-DE")

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert b"Schnellstart" in response.data
    assert b"Wen m" in response.data
    assert b"Meine AI Matches zeigen" in response.data


def test_onboarding_page_uses_secondary_supported_device_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "sv-SE,sv;q=0.9,en-US;q=0.8")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"Quick start" in response.data


def test_onboarding_page_supports_arabic_rtl_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "ar-AE,ar;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="ar" dir="rtl">' in response.data
    assert "بداية سريعة".encode("utf-8") in response.data
    assert "عرض AI Matches الخاصة بي".encode("utf-8") in response.data


def test_onboarding_page_supports_french_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "fr-FR,fr;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="fr" dir="ltr">' in response.data
    assert "Démarrage rapide".encode("utf-8") in response.data
    assert "Afficher mes AI Matches".encode("utf-8") in response.data


def test_onboarding_page_supports_italian_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "it-IT,it;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="it" dir="ltr">' in response.data
    assert "Avvio rapido".encode("utf-8") in response.data
    assert "Mostra i miei AI Matches".encode("utf-8") in response.data


def test_onboarding_page_supports_indonesian_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "id-ID,id;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="id" dir="ltr">' in response.data
    assert "Mulai cepat".encode("utf-8") in response.data
    assert "Tampilkan AI Matches saya".encode("utf-8") in response.data


def test_onboarding_page_supports_japanese_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "ja-JP,ja;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="ja" dir="ltr">' in response.data
    assert "クイックスタート".encode("utf-8") in response.data
    assert "自分の AI Matches を表示".encode("utf-8") in response.data


def test_onboarding_page_supports_korean_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "ko-KR,ko;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="ko" dir="ltr">' in response.data
    assert "빠른 시작".encode("utf-8") in response.data
    assert "내 AI Matches 보기".encode("utf-8") in response.data


def test_onboarding_page_supports_dutch_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "nl-NL,nl;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="nl" dir="ltr">' in response.data
    assert "Snelle start".encode("utf-8") in response.data
    assert "Toon mijn AI Matches".encode("utf-8") in response.data


def test_onboarding_page_supports_romanian_language(monkeypatch):
    response = _open_onboarding(monkeypatch, "ro-RO,ro;q=0.9")

    assert response.status_code == 200
    assert b'<html lang="ro" dir="ltr">' in response.data
    assert "Start rapid".encode("utf-8") in response.data
    assert "Arată AI Matches mele".encode("utf-8") in response.data
