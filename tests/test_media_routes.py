from io import BytesIO

import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def test_media_page_renders_current_avatar(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/media/alice@example.com")

    assert response.status_code == 200
    assert b"Alice" in response.data
    assert b"/avatar/alice@example.com.png" in response.data


def test_media_page_upload_saves_avatar_and_removes_old_file(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    old_avatar = tmp_path / "alice_at_example_com.jpg"
    old_avatar.write_bytes(b"old")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "ALLOWED_EXTENSIONS", {"png", "jpg"})
    monkeypatch.setattr(app, "allowed_mime_type", lambda file: True)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/media/alice@example.com",
        data={
            "csrf_token": "token-1",
            "avatar": (BytesIO(b"new image"), "avatar.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Аватар успешно загружен.".encode("utf-8") in response.data
    assert not old_avatar.exists()
    assert (tmp_path / "alice_at_example_com.png").exists()


def test_quick_avatar_upload_redirects_and_saves_avatar(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    old_avatar = tmp_path / "alice_at_example_com.jpg"
    old_avatar.write_bytes(b"old")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "ALLOWED_EXTENSIONS", {"png", "jpg"})
    monkeypatch.setattr(app, "allowed_mime_type", lambda file: True)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/quick_avatar/alice@example.com",
        data={
            "csrf_token": "token-1",
            "avatar": (BytesIO(b"new image"), "avatar.png"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/alice@example.com")
    assert not old_avatar.exists()
    assert (tmp_path / "alice_at_example_com.png").exists()


def test_quick_avatar_rejects_invalid_extension(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    events = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": events.append((event_type, email, details)))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/quick_avatar/alice@example.com",
        data={
            "csrf_token": "token-1",
            "avatar": (BytesIO(b"bad"), "avatar.exe"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.data == b"Unsupported avatar file type"
    assert events == [("upload_rejected", "alice@example.com", "Unsupported avatar file extension")]
