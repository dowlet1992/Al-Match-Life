import app
from backend.models import User


def make_user(email="alice@example.com", password="old-password-123"):
    user = User("Alice", 28, email, password, "Germany", "", "", "", [], [], [], [])
    app.set_user_password(user, password)
    return user


def login(client, email="alice@example.com", language="en"):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"
        session["language"] = language


def test_change_password_page_requires_owner(monkeypatch):
    alice = make_user()
    bob = make_user("bob@example.com")

    monkeypatch.setattr(app, "users", [alice, bob])

    client = app.app.test_client()
    login(client)

    response = client.get("/settings/bob@example.com/password")

    assert response.status_code == 403


def test_change_password_page_shows_security_form(monkeypatch):
    user = make_user()

    monkeypatch.setattr(app, "users", [user])

    client = app.app.test_client()
    login(client)

    response = client.get("/settings/alice@example.com/password", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"Change password" in response.data
    assert b'name="current_password"' in response.data
    assert b'name="new_password"' in response.data
    assert b'name="confirm_password"' in response.data


def test_change_password_rejects_wrong_current_password(monkeypatch):
    user = make_user()
    saved_users = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: saved_users.append(users))
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login(client)

    response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "current_password": "wrong-password",
            "new_password": "new-password-456",
            "confirm_password": "new-password-456",
        },
    )

    assert response.status_code == 200
    assert b"Current password is incorrect." in response.data
    assert app.verify_user_password(user, "old-password-123") is True
    assert app.verify_user_password(user, "new-password-456") is False
    assert saved_users == []


def test_change_password_rejects_short_or_mismatched_new_password(monkeypatch):
    user = make_user()

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login(client)

    short_response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "current_password": "old-password-123",
            "new_password": "short",
            "confirm_password": "short",
        },
    )
    mismatch_response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "current_password": "old-password-123",
            "new_password": "new-password-456",
            "confirm_password": "another-password-456",
        },
    )

    assert short_response.status_code == 200
    assert b"New password must be at least 8 characters." in short_response.data
    assert mismatch_response.status_code == 200
    assert b"New passwords do not match." in mismatch_response.data
    assert app.verify_user_password(user, "old-password-123") is True


def test_change_password_updates_hash_and_clears_login_attempts(monkeypatch):
    user = make_user()
    saved_users = []
    cleared_attempts = []
    security_events = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: saved_users.append(users))
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: cleared_attempts.append(email))
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: security_events.append(args))

    client = app.app.test_client()
    login(client)

    response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "current_password": "old-password-123",
            "new_password": "new-password-456",
            "confirm_password": "new-password-456",
        },
    )

    assert response.status_code == 200
    assert b"Password changed successfully." in response.data
    assert app.verify_user_password(user, "new-password-456") is True
    assert app.verify_user_password(user, "old-password-123") is False
    assert saved_users
    assert cleared_attempts == ["alice@example.com"]
    assert security_events[-1][0] == "password_changed"


def test_change_password_with_2fa_sends_code_and_requires_valid_code(monkeypatch):
    user = make_user()
    saved_users = []
    sent_codes = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: saved_users.append(users))
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"two_factor_required": True})
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: sent_codes.append((contact_type, contact_value, code)) or True)
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: code == "123456")

    client = app.app.test_client()
    login(client)

    send_response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "action": "send_security_code",
            "current_password": "old-password-123",
        },
    )
    invalid_response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "action": "change_password",
            "current_password": "old-password-123",
            "new_password": "new-password-456",
            "confirm_password": "new-password-456",
            "confirmation_code": "000000",
        },
    )

    assert send_response.status_code == 200
    assert b"Security code sent." in send_response.data
    assert sent_codes == [("email", "alice@example.com", "123456")]
    assert b"Security code is invalid or expired." in invalid_response.data
    assert app.verify_user_password(user, "old-password-123") is True

    valid_response = client.post(
        "/settings/alice@example.com/password",
        data={
            "csrf_token": "token-1",
            "action": "change_password",
            "current_password": "old-password-123",
            "new_password": "new-password-456",
            "confirm_password": "new-password-456",
            "confirmation_code": "123456",
        },
    )

    assert valid_response.status_code == 200
    assert b"Password changed successfully." in valid_response.data
    assert app.verify_user_password(user, "new-password-456") is True
    assert saved_users
