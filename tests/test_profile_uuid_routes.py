import app
from backend.models import User


def test_profile_route_accepts_uuid_and_legacy_email(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    uuid_response = client.get(f"/profile/{alice.id}")
    legacy_response = client.get(f"/profile/{alice.email}")

    assert uuid_response.status_code == 200
    assert legacy_response.status_code == 200
    assert alice.id.encode() in uuid_response.data


def test_dashboard_generates_uuid_profile_links(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email
    response = client.get(f"/dashboard/{alice.email}")

    assert response.status_code == 200
    assert f'href="/profile/{alice.id}"'.encode() in response.data


def test_dashboard_accepts_uuid_and_generates_uuid_story_links(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Designer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": []})
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": [{
        "email": bob.email,
        "created_at": app.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }]})
    monkeypatch.setattr(app, "can_view_user_stories", lambda viewer, owner: True)
    monkeypatch.setattr(app, "generate_life_radar", lambda user: [])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email
    response = client.get(f"/dashboard/{alice.id}")

    assert response.status_code == 200
    assert f'/create_story/{alice.id}'.encode() in response.data
    assert f'/story/{alice.id}/{bob.id}'.encode() in response.data
    assert b'/story/alice@example.com/bob@example.com' not in response.data


def test_dashboard_rejects_another_users_identifier(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    response = client.get(f"/dashboard/{bob.id}")

    assert response.status_code == 403


def test_private_profile_message_uses_viewer_language(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Designer", "", [], [], [], [])
    alice.language = "de"
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "profile_visibility": "private" if email == bob.email else "public",
    })
    monkeypatch.setattr(app, "are_friends", lambda one, two: False)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email
    response = client.get(f"/profile/{bob.id}?viewer={alice.id}")

    assert response.status_code == 200
    assert "Privates Profil".encode() in response.data
    assert "Diese Person hat ihr Profil auf privat gestellt".encode() in response.data
    assert "Профиль закрыт".encode() not in response.data


def test_profile_uuid_viewer_cannot_impersonate_another_session_user(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "Designer", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    response = client.get(f"/profile/{alice.id}?viewer={bob.id}")

    assert response.status_code == 200
    assert "Доступ закрыт".encode() in response.data
