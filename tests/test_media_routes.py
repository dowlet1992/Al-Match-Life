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
    assert (tmp_path / f"{alice.id}.png").exists()
    assert not (tmp_path / "alice_at_example_com.png").exists()


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
    assert (tmp_path / f"{alice.id}.png").exists()
    assert not (tmp_path / "alice_at_example_com.png").exists()


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


def test_media_file_streaming_supports_ranges_and_safe_cache_headers(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    media_file = tmp_path / "sample.mp4"
    media_file.write_bytes(b"0123456789")
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(
        "/media-files/sample.mp4",
        headers={"Range": "bytes=2-5"},
    )

    assert response.status_code == 206
    assert response.data == b"2345"
    assert response.headers["Content-Range"] == "bytes 2-5/10"
    assert response.headers["Accept-Ranges"] == "bytes"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "private, max-age=86400"


def test_media_streaming_falls_back_to_legacy_static_uploads(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    current_folder = tmp_path / "current"
    legacy_folder = tmp_path / "legacy"
    current_folder.mkdir()
    legacy_folder.mkdir()
    (legacy_folder / "existing.jpg").write_bytes(b"legacy-media")
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(current_folder))
    monkeypatch.setattr(app, "LEGACY_UPLOAD_FOLDER", str(legacy_folder))

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get("/media-files/existing.jpg")

    assert response.status_code == 200
    assert response.data == b"legacy-media"
    assert response.headers["Accept-Ranges"] == "bytes"


def test_media_streaming_rejects_unauthenticated_requests(monkeypatch, tmp_path):
    (tmp_path / "private.jpg").write_bytes(b"private")
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))

    response = app.app.test_client().get("/media-files/private.jpg")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_chat_media_is_available_only_to_conversation_participants(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    charlie = User("Charlie", 30, "charlie@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    filename = f"chat_{alice.id}_token_20260730101010123456.png"
    (tmp_path / filename).write_bytes(b"private-chat-media")
    messages = [{
        "id": 1,
        "from": alice.email,
        "to": bob.email,
        "media_url": f"/media-files/{filename}",
        "media_type": "image",
    }]
    monkeypatch.setattr(app, "users", [alice, bob, charlie])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "load_messages", lambda: messages)

    alice_client = app.app.test_client()
    login(alice_client, alice.email)
    assert alice_client.get(f"/media-files/{filename}").status_code == 200

    bob_client = app.app.test_client()
    login(bob_client, bob.email)
    assert bob_client.get(f"/media-files/{filename}").status_code == 200

    charlie_client = app.app.test_client()
    login(charlie_client, charlie.email)
    assert charlie_client.get(f"/media-files/{filename}").status_code == 404


def test_story_media_respects_owner_privacy(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    filename = f"story_{alice.id}_token_20260730101010123456.jpg"
    (tmp_path / filename).write_bytes(b"story-media")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "load_stories", lambda: {
        "stories": [{"email": alice.email, "media_url": f"/media-files/{filename}"}],
    })
    monkeypatch.setattr(app, "can_view_user_stories", lambda viewer, owner: viewer == owner)

    owner_client = app.app.test_client()
    login(owner_client, alice.email)
    assert owner_client.get(f"/media-files/{filename}").status_code == 200

    other_client = app.app.test_client()
    login(other_client, bob.email)
    assert other_client.get(f"/media-files/{filename}").status_code == 404


def test_feed_media_respects_post_visibility(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    filename = f"post_{alice.id}_token_20260730101010123456.mp4"
    media_url = f"/media-files/{filename}"
    post = {"id": 1, "email": alice.email, "media_url": media_url, "media_items": [{"url": media_url}]}
    (tmp_path / filename).write_bytes(b"post-media")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": [post]})
    monkeypatch.setattr(app, "can_view_feed_post", lambda viewer, selected_post: viewer == alice.email)

    owner_client = app.app.test_client()
    login(owner_client, alice.email)
    assert owner_client.get(media_url).status_code == 200

    other_client = app.app.test_client()
    login(other_client, bob.email)
    assert other_client.get(media_url).status_code == 404


def test_media_streaming_route_is_owned_by_media_blueprint():
    endpoint = next(
        rule.endpoint
        for rule in app.app.url_map.iter_rules()
        if rule.rule == "/media-files/<path:filename>"
    )

    assert endpoint == "media_routes.stream_media_file"


def test_avatar_url_prefers_uuid_and_keeps_legacy_email_fallback(monkeypatch, tmp_path):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(app, "ALLOWED_EXTENSIONS", {"png"})

    legacy = tmp_path / "alice_at_example_com.png"
    legacy.write_bytes(b"legacy")
    assert app.get_avatar_url(alice.email) == "/media-files/alice_at_example_com.png"

    uuid_avatar = tmp_path / f"{alice.id}.png"
    uuid_avatar.write_bytes(b"uuid")
    assert app.get_avatar_url(alice.email) == f"/media-files/{alice.id}.png"
    assert alice.email not in app.get_avatar_url(alice.email)
