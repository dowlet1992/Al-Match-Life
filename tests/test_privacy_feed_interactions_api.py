import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email


def test_api_privacy_get_and_update(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    privacy_store = {}

    monkeypatch.setattr(app, "users", [alice])

    def fake_normalize(email):
        defaults = {
            "show_in_search": True,
            "private_profile": False,
            "ai_recommendations": True,
            "ai_life_radar": True,
            "recommend_my_profile": True,
            "ai_activity_analysis": True,
            "notifications_enabled": True,
            "message_permission": "everyone",
        }
        defaults.update(privacy_store.get(email, {}))
        return defaults

    monkeypatch.setattr(app, "normalize_user_ai_settings", fake_normalize)
    monkeypatch.setattr(app, "save_user_ai_settings", lambda email, settings: privacy_store.update({email: settings}))

    client = app.app.test_client()
    login(client, "alice@example.com")

    get_response = client.get("/api/privacy")
    assert get_response.status_code == 200
    assert get_response.get_json()["settings"]["show_in_search"] is True

    update_response = client.patch(
        "/api/privacy",
        json={"show_in_search": False, "message_permission": "friends"},
    )

    assert update_response.status_code == 200
    settings = update_response.get_json()["settings"]
    assert settings["show_in_search"] is False
    assert settings["message_permission"] == "friends"


def test_api_privacy_audits_server_transcription_consent(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    store = {"allow_server_call_transcription": False}
    events = []
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: app.privacy_service.normalize_settings(store))
    monkeypatch.setattr(app, "save_user_ai_settings", lambda email, settings: store.update(settings))
    monkeypatch.setattr(app, "log_security_event", lambda event, email="", details="": events.append((event, email)))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.patch("/api/privacy", json={"allow_server_call_transcription": True})

    assert response.status_code == 200
    assert store["server_transcription_consent_at"]
    assert store["server_transcription_consent_revoked_at"] == ""
    assert events == [("server_transcription_consent_granted", alice.email)]


def test_api_feed_like_comment_and_save(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    feed_store = {
        "posts": [
            {
                "id": 1,
                "email": "bob@example.com",
                "name": "Bob",
                "type": "Идея",
                "text": "AI network post",
                "hashtags": [],
                "language": "en",
                "likes": [],
                "comments": [],
                "saves": [],
                "shares": [],
            }
        ]
    }
    signals = []

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "record_ai_feed_signal", lambda email, post, action: signals.append(action))

    client = app.app.test_client()
    login(client, "alice@example.com")

    like_response = client.post("/api/feed/posts/1/like")
    assert like_response.status_code == 200
    assert like_response.get_json()["liked"] is True
    assert like_response.get_json()["post"]["liked"] is True
    assert feed_store["posts"][0]["likes"] == ["alice@example.com"]

    comment_response = client.post("/api/feed/posts/1/comment", json={"text": "Great idea"})
    assert comment_response.status_code == 201
    assert comment_response.get_json()["comment"]["text"] == "Great idea"
    assert comment_response.get_json()["post"]["comments_count"] == 1
    assert feed_store["posts"][0]["comments"][0]["author"] == "alice@example.com"

    save_response = client.post("/api/feed/posts/1/save")
    assert save_response.status_code == 200
    assert save_response.get_json()["saved"] is True
    assert save_response.get_json()["post"]["saved"] is True
    assert feed_store["posts"][0]["saves"] == ["alice@example.com"]
    assert signals == ["like_post", "comment_post", "save_post"]

    oversized = client.post("/api/feed/posts/1/comment", json={"text": "x" * 1001})
    assert oversized.status_code == 400


def test_api_feed_uses_viewer_content_and_relationship_filters(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    carol = User("Carol", 32, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    feed_store = {
        "posts": [
            {"id": 1, "email": "bob@example.com", "text": "Visible idea", "likes": [], "comments": [], "saves": []},
            {"id": 2, "email": "bob@example.com", "text": "Adult idea", "content_rating": "adult", "likes": [], "comments": [], "saves": []},
            {"id": 3, "email": "carol@example.com", "text": "Restricted idea", "likes": [], "comments": [], "saves": []},
        ]
    }

    monkeypatch.setattr(app, "users", [alice, bob, carol])
    monkeypatch.setattr(app, "load_feed", lambda: feed_store)
    monkeypatch.setattr(app, "save_feed", lambda data: feed_store.update(data))
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"alice@example.com": ["carol@example.com"]}})
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "adult_content_filter": True,
        "sensitive_content_filter": True,
    })

    client = app.app.test_client()
    login(client, "alice@example.com")

    list_response = client.get("/api/feed")
    assert list_response.status_code == 200
    listed_texts = [post["text"] for post in list_response.get_json()["posts"]]
    assert listed_texts == ["Visible idea"]

    adult_like_response = client.post("/api/feed/posts/2/like")
    restricted_like_response = client.post("/api/feed/posts/3/like")
    assert adult_like_response.status_code == 403
    assert restricted_like_response.status_code == 403
