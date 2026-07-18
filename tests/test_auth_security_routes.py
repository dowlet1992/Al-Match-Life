import app
from backend.models import User


def make_user(email="alice@example.com", password="old-password-123"):
    user = User("Alice", 28, email, password, "Germany", "", "Engineer", "", [], [], [], [])
    app.set_user_password(user, password)
    return user


def set_csrf(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"


def set_login_2fa_session(client, email="alice@example.com"):
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"
        session["language"] = "en"
        session["pending_2fa_email"] = email
        session["pending_2fa_contact_type"] = "email"
        session["pending_2fa_contact_value"] = email


def login(client, email="alice@example.com"):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def test_verify_login_2fa_success_starts_user_session(monkeypatch):
    alice = make_user()
    events = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: code == "123456")
    monkeypatch.setattr(app, "bind_session_to_user", lambda user: None)
    monkeypatch.setattr(app, "record_trusted_device_seen", lambda user: None)
    monkeypatch.setattr(app, "send_login_alert", lambda user: None)
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": events.append((event_type, email, details)))

    client = app.app.test_client()
    set_login_2fa_session(client)

    response = client.post("/verify_login_2fa", data={"csrf_token": "token-1", "code": "123456"})

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/onboarding/alice@example.com")
    with client.session_transaction() as session:
        assert session["user_email"] == "alice@example.com"
        assert session["csrf_token"] == "token-1"
        assert session["language"] == "en"
    assert ("login_2fa_success", "alice@example.com", "via=email") in events


def test_verify_login_2fa_missing_session_returns_400(monkeypatch):
    logs = []
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": logs.append((event_type, email, details)))

    client = app.app.test_client()
    response = client.get("/verify_login_2fa")

    assert response.status_code == 400
    assert logs == [("login_2fa_session_missing", "", "pending 2FA session is missing")]


def test_forgot_password_sends_reset_code_without_disclosing_account(monkeypatch):
    alice = make_user()
    sent_codes = []

    monkeypatch.setattr(app, "find_user_by_contact", lambda contact_type, contact_value: alice)
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: sent_codes.append((contact_type, contact_value, code)))
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/forgot_password",
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "contact_value": "alice@example.com",
        },
    )

    assert response.status_code == 200
    assert "Если аккаунт найден".encode("utf-8") in response.data
    assert sent_codes == [("email", "alice@example.com", "123456")]


def test_reset_password_updates_password_and_clears_attempts(monkeypatch):
    alice = make_user()
    saved_users = []
    cleared = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "find_user_by_contact", lambda contact_type, contact_value: alice)
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: code == "123456")
    monkeypatch.setattr(app, "save_users_to_json", lambda users_value: saved_users.append(list(users_value)))
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: cleared.append(email))
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/reset_password",
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "contact_value": "alice@example.com",
            "code": "123456",
            "new_password": "new-password-456",
        },
    )

    assert response.status_code == 200
    assert "Пароль успешно изменён".encode("utf-8") in response.data
    assert app.verify_user_password(alice, "new-password-456") is True
    assert saved_users
    assert cleared == ["alice@example.com"]


def test_reset_password_rejects_missing_csrf(monkeypatch):
    monkeypatch.setattr(app, "users", [make_user()])

    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/reset_password",
        data={
            "contact_type": "email",
            "contact_value": "alice@example.com",
            "code": "123456",
            "new_password": "new-password-456",
        },
    )

    assert response.status_code == 403


def test_logout_clears_session(monkeypatch):
    alice = make_user()
    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()
    login(client)

    response = client.get("/logout")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as session:
        assert "user_email" not in session
