import app
from backend.auth_tokens import create_access_token
from backend.models import User


def test_api_auth_register_creates_unverified_user(monkeypatch):
    saved_users = []
    monkeypatch.setattr(app, "users", saved_users)
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: True)

    client = app.app.test_client()
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Alice",
            "age": 28,
            "country": "Germany",
            "contact_type": "email",
            "email": "alice@example.com",
            "password": "strongpass123",
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["ok"] is True
    assert data["verification_required"] is True
    assert data["delivery_sent"] is True
    assert data["user"]["email"] == "alice@example.com"
    assert len(saved_users) == 1
    assert saved_users[0].account_verified is False
    assert saved_users[0].password != "strongpass123"


def test_api_auth_login_sets_session_for_verified_user(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "", "Germany", "", "", "", [], [], [], [])
    app.set_user_password(user, "strongpass123")
    user.account_verified = True
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)

    client = app.app.test_client()
    response = client.post(
        "/api/auth/login",
        json={"login": "alice@example.com", "password": "strongpass123"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["authenticated"] is True
    assert data["user"]["email"] == "alice@example.com"
    assert data["token_type"] == "Bearer"
    assert data["access_token"]
    assert data["expires_in"] > 0

    with client.session_transaction() as session:
        assert session["user_email"] == "alice@example.com"


def test_api_auth_login_requires_verification_for_unverified_user(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "", "Germany", "", "", "", [], [], [], [])
    app.set_user_password(user, "strongpass123")
    user.account_verified = False
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: True)

    client = app.app.test_client()
    response = client.post(
        "/api/auth/login",
        json={"login": "alice@example.com", "password": "strongpass123"},
    )

    assert response.status_code == 403
    data = response.get_json()
    assert data["ok"] is True
    assert data["authenticated"] is False
    assert data["verification_required"] is True


def test_api_auth_verify_marks_user_verified_and_logs_in(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "", "Germany", "", "", "", [], [], [], [])
    user.account_verified = False
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: True)

    client = app.app.test_client()
    response = client.post(
        "/api/auth/verify",
        json={
            "purpose": "account_verify",
            "contact_type": "email",
            "contact_value": "alice@example.com",
            "code": "123456",
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["verified"] is True
    assert data["authenticated"] is True
    assert user.account_verified is True
    assert data["token_type"] == "Bearer"
    assert data["access_token"]

    with client.session_transaction() as session:
        assert session["user_email"] == "alice@example.com"


def test_api_auth_logout_clears_session():
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    with client.session_transaction() as session:
        assert "user_email" not in session


def test_api_me_accepts_bearer_access_token(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    token = create_access_token("alice@example.com", app.app.secret_key, expires_in_seconds=600)

    client = app.app.test_client()
    response = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["user"]["email"] == "alice@example.com"


def test_api_me_rejects_invalid_bearer_token(monkeypatch):
    monkeypatch.setattr(app, "users", [])

    client = app.app.test_client()
    response = client.get("/api/me", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401
    assert response.get_json()["error"] == "Authentication required"
