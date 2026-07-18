import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email, name="Alice", profession="Founder"):
    return User(
        name,
        28,
        email,
        "hashed",
        "Germany",
        "Bio",
        profession,
        "Partners",
        ["English"],
        ["Build"],
        ["AI"],
        ["Sales"],
    )


def test_feed_page_renders_create_form_and_ranked_post(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob", "Architect")
    feed_store = {
        "posts": [
            {
                "id": 1,
                "email": "bob@example.com",
                "language": "en",
                "type": "Idea",
                "text": "AI product for founders",
                "location": "Berlin",
                "hashtags": ["ai"],
                "likes": [],
                "comments": [],
                "saves": [],
            }
        ]
    }

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "can_view_feed_post", lambda viewer_email, post: True)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "calculate_ai_learning_boost", lambda user_email, post, content_language: (0, []))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/feed/alice@example.com")

    assert response.status_code == 200
    assert b"AI Discover" in response.data
    assert b"/create_post/alice@example.com" in response.data
    assert b"AI product for founders" in response.data
    assert b"/avatar/bob@example.com.png" in response.data


def test_feed_page_renders_empty_state(monkeypatch):
    alice = make_user("alice@example.com", "Alice")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/feed/alice@example.com")

    assert response.status_code == 200
    assert "Пока нет публикаций".encode("utf-8") in response.data


def test_feed_page_uses_saved_turkish_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "tr"

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/feed/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Paylaşım oluştur".encode("utf-8") in response.data
    assert "AI Discover'da paylaş".encode("utf-8") in response.data
    assert "Henüz paylaşım yok".encode("utf-8") in response.data
    assert "Dilleriniz".encode("utf-8") in response.data
    assert "Создать публикацию".encode("utf-8") not in response.data
    assert "Опубликовать".encode("utf-8") not in response.data
    assert "Пока нет публикаций".encode("utf-8") not in response.data
    assert "Ваши языки".encode("utf-8") not in response.data


def test_create_post_route_saves_post_and_records_ai_signal(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    feed_store = {"posts": []}
    saved_payloads = []
    signals = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: saved_payloads.append(data.copy()))
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append((email, post.get("id"), action)))
    monkeypatch.setattr(app, "detect_content_language", lambda text: "en")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/create_post/alice@example.com",
        data={
            "csrf_token": "token-1",
            "type": "project",
            "text": "Global matching platform",
            "hashtags": "#ai #network",
            "return_to": "feed",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/feed/alice@example.com")
    assert saved_payloads
    assert feed_store["posts"][0]["type"] == "Проект"
    assert feed_store["posts"][0]["hashtags"] == ["ai", "network"]
    assert signals == [("alice@example.com", 1, "create_post")]
