import app
from backend.models import User


def test_people_controls_lists_blocked_restricted_and_hidden_story_users(monkeypatch):
    owner = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    blocked = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    restricted = User("Carol", 30, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    hidden = User("Dana", 29, "dana@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [owner, blocked, restricted, hidden])
    monkeypatch.setattr(app, "load_blocks", lambda: {"blocks": {"alice@example.com": ["bob@example.com"]}})
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"alice@example.com": ["carol@example.com"]}})
    monkeypatch.setattr(app, "load_hidden_stories", lambda: {"hidden_stories": {"alice@example.com": ["dana@example.com"]}})

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/settings/alice@example.com/people_controls")

    assert response.status_code == 200
    assert b"bob@example.com" in response.data
    assert b"carol@example.com" in response.data
    assert b"dana@example.com" in response.data


def test_people_controls_actions_update_lists(monkeypatch):
    saved_blocks = []
    saved_restrictions = []
    saved_hidden = []

    monkeypatch.setattr(app, "users", [
        User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], []),
        User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], []),
    ])
    monkeypatch.setattr(app, "load_blocks", lambda: {"blocks": {"alice@example.com": ["bob@example.com"]}})
    monkeypatch.setattr(app, "save_blocks", lambda data: saved_blocks.append(data))
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"alice@example.com": ["bob@example.com"]}})
    monkeypatch.setattr(app, "save_restrictions", lambda data: saved_restrictions.append(data))
    monkeypatch.setattr(app, "load_hidden_stories", lambda: {"hidden_stories": {"alice@example.com": ["bob@example.com"]}})
    monkeypatch.setattr(app, "save_hidden_stories", lambda data: saved_hidden.append(data))

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"

    form = {"csrf_token": "token-1"}
    assert client.post("/settings/alice@example.com/people_controls/unblock/bob@example.com", data=form).status_code == 302
    assert client.post("/settings/alice@example.com/people_controls/unrestrict/bob@example.com", data=form).status_code == 302
    assert client.post("/settings/alice@example.com/people_controls/show_stories/bob@example.com", data=form).status_code == 302

    assert saved_blocks[-1]["blocks"]["alice@example.com"] == []
    assert saved_restrictions[-1]["restrictions"]["alice@example.com"] == []
    assert saved_hidden[-1]["hidden_stories"]["alice@example.com"] == []


def test_people_controls_reject_other_users(monkeypatch):
    monkeypatch.setattr(app, "users", [
        User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], []),
        User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], []),
    ])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"

    assert client.get("/settings/bob@example.com/people_controls").status_code == 403
    assert client.post("/settings/bob@example.com/people_controls/unblock/alice@example.com", data={"csrf_token": "token-1"}).status_code == 403
