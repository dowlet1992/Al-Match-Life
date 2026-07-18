import app
from backend.models import User


def make_user(email, language="tr"):
    user = User("Alice", 28, email, "hashed", "Germany", "", "Founder", "", [], [], [], [])
    user.language = language
    return user


def test_proof_profile_uses_viewer_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "tr")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_proofs", lambda: {"proofs": [
        {"email": "alice@example.com", "type": "video"},
        {"email": "alice@example.com", "type": "photo"},
    ]})

    client = app.app.test_client()

    response = client.get("/proof/alice@example.com/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Video kanıtları".encode("utf-8") in response.data
    assert "Fotoğraflar ve projeler".encode("utf-8") in response.data
    assert "Bu kullanıcı".encode("utf-8") in response.data
    assert "Видео-доказательства".encode("utf-8") not in response.data
    assert "Пользователь загрузил".encode("utf-8") not in response.data


def test_add_proof_page_uses_viewer_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "tr")

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()

    response = client.get("/add_proof/alice@example.com/alice@example.com/video", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Proof ekle".encode("utf-8") in response.data
    assert "Başlık".encode("utf-8") in response.data
    assert "Kaydet".encode("utf-8") in response.data
    assert "Добавить Proof".encode("utf-8") not in response.data
    assert "Название".encode("utf-8") not in response.data
