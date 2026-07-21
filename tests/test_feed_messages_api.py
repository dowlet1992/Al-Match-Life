import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email


def test_api_feed_create_and_list_posts(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    feed_store = {"posts": []}

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda user_email, post, action_type: None)

    client = app.app.test_client()
    login(client, "alice@example.com")

    create_response = client.post(
        "/api/feed/posts",
        json={
            "type": "Идея",
            "text": "Building a useful AI network",
            "hashtags": ["ai", "startup"],
            "location": "Berlin",
            "language": "en",
        },
    )

    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["ok"] is True
    assert created["post"]["text"] == "Building a useful AI network"
    assert created["post"]["hashtags"] == ["ai", "startup"]

    list_response = client.get("/api/feed")
    assert list_response.status_code == 200
    listed = list_response.get_json()
    assert listed["ok"] is True
    assert len(listed["posts"]) == 1
    assert listed["posts"][0]["author"]["email"] == "alice@example.com"


def test_api_feed_cursor_pagination_is_bounded_and_rejects_invalid_cursor(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    feed_store = {"posts": [
        {"id": str(index), "email": "alice@example.com", "text": f"Post {index}", "likes": [], "comments": [], "saves": []}
        for index in range(1, 4)
    ]}
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    client = app.app.test_client()
    login(client, "alice@example.com")

    first = client.get("/api/feed?limit=2")
    assert first.status_code == 200
    first_data = first.get_json()
    assert first.headers["Cache-Control"] == "private, no-store"
    assert [post["id"] for post in first_data["posts"]] == ["3", "2"]
    assert first_data["next_cursor"]

    second = client.get("/api/feed", query_string={"limit": 2, "cursor": first_data["next_cursor"]})
    assert second.status_code == 200
    assert [post["id"] for post in second.get_json()["posts"]] == ["1"]
    assert second.get_json()["next_cursor"] is None
    assert client.get("/api/feed?limit=0").status_code == 400
    assert client.get("/api/feed?cursor=%%%bad").status_code == 400
    assert client.get("/api/feed?cursor=YWJj").status_code == 400


def test_api_chat_messages_send_and_list(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    message_store = []
    notifications = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: message_store)
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(
        app,
        "create_social_notification",
        lambda target_email, text, notification_type="social", from_email="": notifications.append(
            {
                "target_email": target_email,
                "text": text,
                "type": notification_type,
                "from_email": from_email,
            }
        ),
    )

    client = app.app.test_client()
    login(client, "alice@example.com")

    send_response = client.post(
        "/api/chats/bob@example.com/messages",
        json={"message": "Hello Bob"},
    )

    assert send_response.status_code == 201
    sent = send_response.get_json()
    assert sent["ok"] is True
    assert sent["message"]["message"] == "Hello Bob"
    assert sent["message"]["mine"] is True
    assert sent["message"]["source_language"] == "en"
    assert notifications[0]["target_email"] == "bob@example.com"

    list_response = client.get("/api/chats/bob@example.com/messages")
    assert list_response.status_code == 200
    listed = list_response.get_json()
    assert listed["ok"] is True
    assert listed["user"]["email"] == "bob@example.com"
    assert len(listed["messages"]) == 1

    chats_response = client.get("/api/chats")
    assert chats_response.status_code == 200
    chats = chats_response.get_json()
    assert chats["ok"] is True
    assert chats["chats"][0]["user"]["email"] == "bob@example.com"


def test_api_chat_rejects_oversized_text(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    message_store = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: message_store)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(f"/api/chats/{bob.email}/messages", json={"message": "x" * 2001})
    assert response.status_code == 400
    assert message_store == []


def test_api_message_translation_is_authorized_and_cached(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    message_store = [{
        "id": 1, "from": bob.email, "to": alice.email, "message": "Hallo",
        "source_language": "de", "translations": {},
    }]
    saves = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: message_store)
    monkeypatch.setattr(app, "save_messages", lambda messages: saves.append(messages))
    monkeypatch.setattr(app, "translate_message_text", lambda text, source, target: "Hello")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.post(
        "/api/chats/bob@example.com/messages/1/translation",
        json={"target_language": "en"},
    )

    assert response.status_code == 200
    assert response.get_json()["translation"]["translated_text"] == "Hello"
    assert message_store[0]["translations"] == {"en": "Hello"}
    assert len(saves) == 1


def test_api_message_translation_does_not_cache_provider_failure(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    message_store = [{
        "id": 1, "from": bob.email, "to": alice.email, "message": "Hallo",
        "source_language": "de", "translations": {},
    }]
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: message_store)
    monkeypatch.setattr(app, "translate_message_text", lambda *args: "")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.post(
        "/api/chats/bob@example.com/messages/1/translation",
        json={"target_language": "en"},
    )

    assert response.status_code == 503
    assert message_store[0]["translations"] == {}


def test_api_chat_automatically_translates_incoming_messages(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    message_store = [
        {"id": 1, "from": bob.email, "to": alice.email, "message": "Hallo", "source_language": "de"},
        {"id": 2, "from": alice.email, "to": bob.email, "message": "Danke", "source_language": "de"},
    ]
    saves = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: message_store)
    monkeypatch.setattr(app, "save_messages", lambda messages: saves.append(messages))
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "auto_translate_messages": True,
        "message_translation_language": "en",
    })
    monkeypatch.setattr(app, "get_openai_status", lambda: {"enabled": True})
    monkeypatch.setattr(app, "translate_message_text", lambda text, source, target: "Hello")

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get("/api/chats/bob@example.com/messages")

    assert response.status_code == 200
    data = response.get_json()
    assert data["messages"][0]["translated_text"] == "Hello"
    assert "translated_text" not in data["messages"][1]
    assert data["auto_translation"]["target_language"] == "en"
    assert len(saves) == 1


def test_api_chat_messages_respects_restrictions(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    message_store = []
    notifications = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_messages", lambda: message_store)
    monkeypatch.setattr(app, "save_messages", lambda messages: None)
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"bob@example.com": ["alice@example.com"]}})
    monkeypatch.setattr(app, "create_social_notification", lambda *args, **kwargs: notifications.append(args))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/api/chats/bob@example.com/messages",
        json={"message": "Hello Bob"},
    )

    assert response.status_code == 403
    assert message_store == []
    assert notifications == []
