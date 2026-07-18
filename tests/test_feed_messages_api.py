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
