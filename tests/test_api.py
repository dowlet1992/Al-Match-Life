import app
from backend.models import User
from backend.social import follow_user


def test_api_health_returns_service_status():
    client = app.app.test_client()

    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["service"] == "AI Match Life"
    assert data["status"] == "healthy"


def test_api_me_requires_authentication():
    client = app.app.test_client()

    response = client.get("/api/me")

    assert response.status_code == 401
    data = response.get_json()
    assert data["ok"] is False
    assert data["error"] == "Authentication required"


def test_api_me_exposes_server_derived_onboarding_state(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = user.email

    initial = client.get("/api/me").get_json()
    assert initial["needs_onboarding"] is True
    assert initial["social"] == {"followers_count": 0, "following_count": 0}
    user.onboarding_skipped = True
    assert client.get("/api/me").get_json()["needs_onboarding"] is False


def test_api_onboarding_updates_current_user(monkeypatch):
    user = User(
        "Alice",
        28,
        "alice@example.com",
        "hashed",
        "Germany",
        "",
        "",
        "",
        [],
        [],
        [],
        [],
    )
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.post(
        "/api/me/onboarding",
        json={
            "looking_for": "business partner",
            "goals": "startup, growth",
            "interests": "AI, product",
            "skills": "sales, strategy",
            "languages": "English, German",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["user"]["onboarding_completed"] is True
    assert data["user"]["looking_for"] == "business partner"
    assert data["user"]["goals"] == ["startup", "growth"]


def test_api_profile_update_changes_matching_fields(monkeypatch):
    user = User(
        "Alice",
        28,
        "alice@example.com",
        "hashed",
        "Germany",
        "",
        "",
        "",
        [],
        [],
        [],
        [],
    )
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.patch(
        "/api/me/profile",
        json={
            "bio": "Building AI products",
            "profession": "Founder",
            "looking_for": "team",
            "skills": ["strategy", "sales"],
            "languages": "English, German",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["user"]["profession"] == "Founder"
    assert data["user"]["skills"] == ["strategy", "sales"]
    assert data["user"]["languages"] == ["English", "German"]


def test_api_matches_returns_ranked_explanations(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Engineer", "Team", ["English"], ["Startup"], ["AI"], ["Kotlin"])
    bob = User("Bob", 29, "bob@example.com", "hashed", "Germany", "", "Designer", "Team", ["English"], ["Startup"], ["AI"], ["Design"])
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    response = client.get("/api/matches")
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["matches"][0]["user"]["email"] == bob.email
    assert data["matches"][0]["score"] >= 0
    assert data["matches"][0]["level"]
    assert data["matches"][0]["reasons"]


def test_api_social_follow_and_friend_request(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    follow_response = client.post("/api/users/bob@example.com/follow")
    assert follow_response.status_code == 200
    follow_data = follow_response.get_json()
    assert follow_data["ok"] is True
    assert follow_data["changed"] is True
    assert follow_data["is_following"] is True
    assert follow_data["follows_you"] is False
    assert follow_data["followers_count"] == 1

    relationship_response = client.get("/api/users/bob@example.com/relationship")
    assert relationship_response.status_code == 200
    assert relationship_response.headers["Cache-Control"] == "private, no-store"
    assert relationship_response.get_json()["relationship"]["is_following"] is True

    request_response = client.post("/api/users/bob@example.com/friend-request")
    assert request_response.status_code == 200
    request_data = request_response.get_json()
    assert request_data["ok"] is True
    assert request_data["changed"] is True
    assert request_data["friend_request_sent"] is True

    with client.session_transaction() as session:
        session["user_email"] = "bob@example.com"

    accept_response = client.post("/api/users/alice@example.com/friend-request/accept")
    assert accept_response.status_code == 200
    accept_data = accept_response.get_json()
    assert accept_data["ok"] is True
    assert accept_data["changed"] is True
    assert accept_data["are_friends"] is True


def test_api_social_lists_are_cursor_paginated_and_relationship_aware(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    carol = User("Carol", 31, "carol@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob, carol])
    follow_user(alice.email, bob.email)
    follow_user(carol.email, bob.email)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = bob.email

    first = client.get("/api/users/bob@example.com/followers?limit=1")
    assert first.status_code == 200
    assert first.headers["Cache-Control"] == "private, no-store"
    first_data = first.get_json()
    assert first_data["kind"] == "followers"
    assert [item["user"]["email"] for item in first_data["items"]] == [alice.email]
    assert first_data["items"][0]["relationship"]["follows_you"] is True
    assert first_data["next_cursor"]

    second = client.get(
        "/api/users/bob@example.com/followers",
        query_string={"limit": 1, "cursor": first_data["next_cursor"]},
    )
    assert second.status_code == 200
    second_data = second.get_json()
    assert [item["user"]["email"] for item in second_data["items"]] == [carol.email]
    assert second_data["next_cursor"] is None
    assert client.get("/api/users/bob@example.com/followers?limit=51").status_code == 400
    assert client.get("/api/users/bob@example.com/followers?cursor=%%%bad").status_code == 400


def test_api_social_lists_respect_profile_privacy_and_blocks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(
        app,
        "normalize_user_ai_settings",
        lambda email: {"profile_visibility": "private" if email == bob.email else "public"},
    )

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    assert client.get("/api/users/bob@example.com/followers").status_code == 403

    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"profile_visibility": "public"})
    monkeypatch.setattr(app, "is_blocked", lambda one, two: one == bob.email and two == alice.email)
    assert client.get("/api/users/bob@example.com/following").status_code == 403


def test_api_notifications_requires_authentication():
    client = app.app.test_client()

    response = client.get("/api/notifications")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False
