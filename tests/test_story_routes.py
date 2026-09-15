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
    assert response.headers["Location"].endswith(f"/dashboard/{alice.id}")
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
    assert "История не добавлена".encode("utf-8") in response.data
    assert stories_store["stories"] == []
    assert logs == [("story_upload_rejected", "alice@example.com", "Unsupported story file extension")]


def test_create_story_rejects_identifier_of_another_user(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(f"/create_story/{bob.id}", data={"csrf_token": "token-1"})

    assert response.status_code == 403


def test_turkish_story_errors_and_viewer_controls_are_localized(monkeypatch, tmp_path):
    import backend.story_routes as story_routes_module

    alice = make_user()
    alice.language = "tr"
    bob = make_user("bob@example.com", "Bob")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "save_stories", lambda data: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    client = app.app.test_client()
    login(client, alice.email)

    invalid_response = client.post(
        f"/create_story/{alice.id}",
        data={"csrf_token": "token-1", "story_media": (BytesIO(b"zip"), "archive.zip")},
        content_type="multipart/form-data",
    )
    monkeypatch.setattr(story_routes_module.story_view_service, "prepare_story_view", lambda *args: {
        "status": "empty", "changed": False, "owner_stories": [], "stories_data": {"stories": []},
    })
    empty_response = client.get(f"/story/{alice.id}/{bob.id}")

    assert invalid_response.status_code == 200
    assert "Hikâye eklenemedi".encode() in invalid_response.data
    assert "Bir fotoğraf veya video ekleyin.".encode() in invalid_response.data
    assert empty_response.status_code == 200
    assert "Henüz hikâye yok".encode() in empty_response.data
    assert "son 24 saat".encode() in empty_response.data


def test_story_rejects_spoofed_viewer_identifier(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/story/{bob.id}/{alice.id}")

    assert response.status_code == 403
