import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email, name):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def test_like_post_route_toggles_like_and_records_signal(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    feed_store = {"posts": [{"id": 1, "email": "bob@example.com", "likes": [], "comments": [], "saves": []}]}
    signals = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append(action))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/like_post/alice@example.com/1", data={"csrf_token": "token-1"})

    assert response.status_code == 302
    assert feed_store["posts"][0]["likes"] == ["alice@example.com"]
    assert signals == ["like_post"]


def test_comment_post_route_adds_comment_with_csrf(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    feed_store = {"posts": [{"id": 1, "email": "bob@example.com", "likes": [], "comments": [], "saves": []}]}
    signals = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append(action))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/comment_post/alice@example.com/1",
        data={"csrf_token": "token-1", "comment": "Great post"},
    )

    assert response.status_code == 302
    assert feed_store["posts"][0]["comments"][0]["text"] == "Great post"
    assert feed_store["posts"][0]["comments"][0]["author"] == "alice@example.com"
    assert signals == ["comment_post"]


def test_save_post_route_toggles_save_and_records_signal(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    feed_store = {"posts": [{"id": 1, "email": "bob@example.com", "likes": [], "comments": [], "saves": []}]}
    signals = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append(action))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/save_post/alice@example.com/1", data={"csrf_token": "token-1"})

    assert response.status_code == 302
    assert feed_store["posts"][0]["saves"] == ["alice@example.com"]
    assert signals == ["save_post"]


def test_post_comments_page_renders_post_and_comments(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    feed_store = {
        "posts": [
            {
                "id": 1,
                "email": "alice@example.com",
                "type": "Idea",
                "text": "Post body",
                "comments": [{"author_name": "Bob", "text": "Nice", "date": "10:00"}],
            }
        ]
    }

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/post_comments/alice@example.com/1")

    assert response.status_code == 200
    assert b"Post body" in response.data
    assert b"Nice" in response.data
    assert b"/comment_post/alice@example.com/1" in response.data


def test_post_page_records_open_signal_and_renders_comments(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    feed_store = {
        "posts": [
            {
                "id": 1,
                "email": "alice@example.com",
                "type": "Idea",
                "text": "Detailed post",
                "date": "Today",
                "comments": [{"author_name": "Bob", "text": "Great", "date": "10:00"}],
            }
        ]
    }
    signals = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append(action))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/post/alice@example.com/1")

    assert response.status_code == 200
    assert b"Detailed post" in response.data
    assert b"Great" in response.data
    assert signals == ["open_post"]


def test_share_post_page_lists_friends(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    feed_store = {"posts": [{"id": 1, "email": "alice@example.com", "type": "Idea", "text": "Share me"}]}

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "get_friends", lambda email: ["bob@example.com"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/share_post/alice@example.com/1")

    assert response.status_code == 200
    assert b"Share me" in response.data
    assert b"Bob" in response.data
    assert b"/send_shared_post/alice@example.com/1/bob@example.com" in response.data


def test_send_shared_post_records_share_and_message(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    feed_store = {"posts": [{"id": 1, "email": "alice@example.com", "text": "Shared post", "shares": []}]}
    messages = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "load_messages", lambda: messages)
    monkeypatch.setattr(app, "save_messages", lambda data: messages[:] if data is messages else messages.extend(data))
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "are_friends", lambda one, two: True)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/send_shared_post/alice@example.com/1/bob@example.com", data={"csrf_token": "token-1"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/chat/alice@example.com/bob@example.com")
    assert feed_store["posts"][0]["shares"][0]["to"] == "bob@example.com"
    assert messages[0]["shared_post_id"] == 1
    assert "Shared post" in messages[0]["message"]


def test_translate_post_page_uses_cached_translation(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    feed_store = {
        "posts": [
            {
                "id": 1,
                "email": "alice@example.com",
                "language": "en",
                "text": "Hello world",
                "ai_translations": {
                    "en->ru": {
                        "source_text": "Hello world",
                        "result": "Привет мир",
                    }
                },
            }
        ]
    }
    signals = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "get_current_language", lambda user: "ru")
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append(action))
    monkeypatch.setattr(app, "generate_ai_translation_summary", lambda *args: "SHOULD NOT RUN")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/translate_post/alice@example.com/1", data={"csrf_token": "token-1"})

    assert response.status_code == 200
    assert "Привет мир".encode("utf-8") in response.data
    assert "Готовый AI-перевод загружен из кэша.".encode("utf-8") in response.data
    assert signals == ["translate_post"]


def test_translate_post_page_creates_and_saves_translation_cache(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    feed_store = {"posts": [{"id": 1, "email": "alice@example.com", "language": "en", "text": "Hello world"}]}
    saved = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: saved.append(data))
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "get_current_language", lambda user: "ru")
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda *args: None)
    monkeypatch.setattr(app, "generate_ai_translation_summary", lambda text, source, target: "Generated translation")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/translate_post/alice@example.com/1", data={"csrf_token": "token-1"})

    assert response.status_code == 200
    assert b"Generated translation" in response.data
    assert saved
    cached = feed_store["posts"][0]["ai_translations"]["en->ru"]
    assert cached["source_text"] == "Hello world"
    assert cached["result"] == "Generated translation"
