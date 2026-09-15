from io import BytesIO

import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email="alice@example.com", name="Alice"):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def test_news_page_renders_existing_news(monkeypatch):
    alice = make_user()
    news_items = [{
        "title": "NOVIX update",
        "body": "New professional news flow",
        "author_name": "Editorial",
        "created_at": "2026-07-18 10:00:00",
        "source": "https://example.com/news",
        "location": "Berlin",
        "media": [{"url": "/static/uploads/news.jpg", "type": "image"}],
    }]

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_news", lambda: news_items)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/news/alice@example.com")

    assert response.status_code == 200
    assert "NOVIX update".encode("utf-8") in response.data
    assert "New professional news flow".encode("utf-8") in response.data
    assert "/static/uploads/news.jpg".encode("utf-8") in response.data


def test_news_page_post_saves_news_and_redirects(monkeypatch):
    alice = make_user()
    news_items = []
    saved_payloads = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_news", lambda: news_items)
    monkeypatch.setattr(app, "save_news", lambda data: saved_payloads.append(list(data)))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/news/alice@example.com",
        data={
            "csrf_token": "token-1",
            "title": "Launch note",
            "body": "Professional news text",
            "source": "https://example.com",
            "location": "Dubai",
        },
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/news/alice@example.com")
    assert saved_payloads
    assert news_items[0]["author_email"] == "alice@example.com"
    assert news_items[0]["title"] == "Launch note"
    assert news_items[0]["media"] == []


def test_news_page_post_saves_uploaded_media(monkeypatch, tmp_path):
    alice = make_user()
    news_items = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_news", lambda: news_items)
    monkeypatch.setattr(app, "save_news", lambda data: None)
    monkeypatch.setattr(app, "allowed_mime_type", lambda uploaded_file: True)
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/news/alice@example.com",
        data={
            "csrf_token": "token-1",
            "title": "Media note",
            "body": "Photo attached",
            "media": (BytesIO(b"image"), "photo.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 303
    assert news_items[0]["media"][0]["type"] == "image"
    media = news_items[0]["media"][0]
    assert media["url"].startswith(f"/media-files/news_{alice.id}_")
    assert media["url"].endswith(".jpg")
    assert alice.email not in media["url"]
    assert "photo" not in media["url"]
    assert media["filename"] == "photo.jpg"
    assert (tmp_path / media["url"].rsplit("/", 1)[-1]).exists()


def test_news_page_rejects_missing_csrf(monkeypatch):
    alice = make_user()

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/news/alice@example.com",
        data={
            "title": "No CSRF",
            "body": "Rejected",
        },
    )

    assert response.status_code == 403


def test_news_page_requires_title_and_body(monkeypatch):
    alice = make_user()
    news_items = []
    saved_payloads = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_news", lambda: news_items)
    monkeypatch.setattr(app, "save_news", lambda data: saved_payloads.append(list(data)))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/news/alice@example.com",
        data={
            "csrf_token": "token-1",
            "title": "",
            "body": "",
        },
    )

    assert response.status_code == 200
    assert "Заполните заголовок и текст.".encode("utf-8") in response.data
    assert saved_payloads == []


def test_news_page_rejects_unsafe_source_url(monkeypatch):
    alice = make_user()
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_news", lambda: [{
        "title": "Unsafe source",
        "body": "Must render without a dangerous link",
        "source": "javascript:alert(1)",
    }])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/news/{alice.email}")

    assert response.status_code == 200
    assert b"javascript:alert" not in response.data


def test_invalid_news_form_does_not_store_uploaded_file(monkeypatch, tmp_path):
    alice = make_user()
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_news", lambda: [])
    monkeypatch.setattr(app, "allowed_mime_type", lambda uploaded_file: True)
    monkeypatch.setattr(app, "UPLOAD_FOLDER", str(tmp_path))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/news/{alice.email}",
        data={
            "csrf_token": "token-1",
            "title": "",
            "body": "",
            "media": (BytesIO(b"image"), "orphan.jpg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert list(tmp_path.iterdir()) == []
