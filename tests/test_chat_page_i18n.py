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


def test_chat_page_uses_saved_turkish_for_primary_interface(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="tr")
    bob = make_user("bob@example.com", "Bob")
    messages = [{
        "id": 1,
        "from": "alice@example.com",
        "to": "bob@example.com",
        "message": "Hello",
        "time": "10:00",
        "status": "sent",
    }]

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: messages)
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))
    monkeypatch.setattr(app, "format_visible_last_seen", lambda viewer_email, owner_email, timestamp: "online")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/chat/alice@example.com/bob@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Sohbette ara".encode("utf-8") in response.data
    assert "Mesajlarda ara...".encode("utf-8") in response.data
    assert "Mesaj yaz...".encode("utf-8") in response.data
    assert "Sesli mesaj".encode("utf-8") in response.data
    assert "Gönder".encode("utf-8") in response.data
    assert "Metin, fotoğraf, video".encode("utf-8") in response.data
    assert "Yanıtla".encode("utf-8") in response.data
    assert "Benden sil".encode("utf-8") in response.data
    assert "Sonuç bulunamadı".encode("utf-8") in response.data
    assert "Tarayıcınız ses kaydını desteklemiyor.".encode("utf-8") in response.data
    assert "Назад".encode("utf-8") not in response.data
    assert "Поиск сообщений".encode("utf-8") not in response.data
    assert "Написать сообщение".encode("utf-8") not in response.data
    assert "Голосовое сообщение".encode("utf-8") not in response.data
    assert "Ответить".encode("utf-8") not in response.data
    assert "Удалить у меня".encode("utf-8") not in response.data
    assert "Ничего не найдено".encode("utf-8") not in response.data


def test_chat_page_renders_typing_status_in_english(monkeypatch):
    alice = make_user("alice@example.com", "Alice", language="en")
    bob = make_user("bob@example.com", "Bob")

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: [])
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(app, "load_typing_status", lambda: {"bob@example.com->alice@example.com": 999999999999})
    monkeypatch.setattr(app, "load_presence_status", lambda: {})
    monkeypatch.setattr(app, "save_presence_status", lambda data: None)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "get_message_permission_status", lambda sender, receiver: (True, "", ""))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/chat/alice@example.com/bob@example.com")

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"typing a message..." in response.data
