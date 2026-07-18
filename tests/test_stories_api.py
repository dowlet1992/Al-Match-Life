import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email


def test_api_stories_tray_respects_story_privacy(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    carol = User("Carol", 31, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    stories_store = {
        "stories": [
            {
                "id": "story-1",
                "email": "bob@example.com",
                "media_url": "/static/bob.jpg",
                "media_type": "image",
                "created_at": app.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "views": [],
            },
            {
                "id": "story-2",
                "email": "carol@example.com",
                "media_url": "/static/carol.jpg",
                "media_type": "image",
                "created_at": app.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "views": [],
            },
        ]
    }

    monkeypatch.setattr(app, "users", [alice, bob, carol])
    monkeypatch.setattr(app, "load_stories", lambda: stories_store)
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "story_visibility": "everyone" if email == "bob@example.com" else "none",
    })

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/api/stories")

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert [entry["user"]["email"] for entry in data["stories"]] == ["bob@example.com"]


def test_api_owner_stories_marks_view_and_blocks_hidden_owner(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    saved_stories = []
    stories_store = {
        "stories": [
            {
                "id": "story-1",
                "email": "bob@example.com",
                "media_url": "/static/bob.jpg",
                "media_type": "image",
                "created_at": app.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "views": [],
            }
        ]
    }

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "load_stories", lambda: stories_store)
    monkeypatch.setattr(app, "save_stories", lambda data: saved_stories.append(data))
    monkeypatch.setattr(app, "load_hidden_stories", lambda: {"hidden_stories": {}})
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"story_visibility": "everyone"})

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/api/stories/bob@example.com")

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["stories"][0]["id"] == "story-1"
    assert saved_stories
    assert stories_store["stories"][0]["views"] == ["alice@example.com"]

    monkeypatch.setattr(app, "load_hidden_stories", lambda: {"hidden_stories": {"alice@example.com": ["bob@example.com"]}})

    blocked_response = client.get("/api/stories/bob@example.com")

    assert blocked_response.status_code == 403
