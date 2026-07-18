from io import BytesIO

import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email="alice@example.com", name="Alice"):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def test_create_story_route_saves_story_and_redirects(monkeypatch, tmp_path):
    alice = make_user()
    stories_store = {"stories": []}
    saved_payloads = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_stories", lambda: stories_store)
    monkeypatch.setattr(app, "save_stories", lambda data: saved_payloads.append(data.copy()))
    monkeypatch.setattr(app, "allowed_mime_type", lambda uploaded_file: True)
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/create_story/alice@example.com",
        data={
            "csrf_token": "token-1",
            "story_media": (BytesIO(b"image"), "photo.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard/alice@example.com")
    assert saved_payloads
    assert stories_store["stories"][0]["email"] == "alice@example.com"
    assert stories_store["stories"][0]["media_type"] == "image"
    assert list(tmp_path.iterdir())


def test_create_story_route_rejects_invalid_story_file(monkeypatch, tmp_path):
    alice = make_user()
    stories_store = {"stories": []}
    logs = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_stories", lambda: stories_store)
    monkeypatch.setattr(app, "save_stories", lambda data: stories_store.update(data))
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email, details: logs.append((event_type, email, details)))
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/create_story/alice@example.com",
        data={
            "csrf_token": "token-1",
            "story_media": (BytesIO(b"zip"), "archive.zip"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Story не добавлена".encode("utf-8") in response.data
    assert stories_store["stories"] == []
    assert logs == [("story_upload_rejected", "alice@example.com", "Unsupported story file extension")]
