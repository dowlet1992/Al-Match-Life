import app
from backend.models import User


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


def test_api_notifications_requires_authentication():
    client = app.app.test_client()

    response = client.get("/api/notifications")

    assert response.status_code == 401
    assert response.get_json()["ok"] is False
