import app
from backend.models import User


def set_csrf(client):
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"


def make_user(email="alice@example.com", name="Alice"):
    return User(name, 28, email, "hashed", "Germany", "", "Engineer", "", [], [], [], [])


def test_register_page_post_creates_unverified_user_and_redirects(monkeypatch):
    created_codes = []
    sent_codes = []
    saved = []
    new_users = []

    monkeypatch.setattr(app, "users", new_users)
    monkeypatch.setattr(app, "save_users_to_json", lambda users_value: saved.append(list(users_value)))
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: created_codes.append((purpose, contact_type, contact_value)) or "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: sent_codes.append((contact_type, contact_value, code)))
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)

    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/register",
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "email": "new@example.com",
            "phone": "",
            "password": "strongpass123",
            "name": "New User",
            "age": "30",
            "country": "Germany",
            "bio": "Builder",
            "profession": "Founder",
            "looking_for": "Partners",
            "languages": "English, German",
            "goals": "Build",
            "interests": "AI",
            "skills": "Product",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/verify_account?contact_type=email&contact_value=new%40example.com")
    assert len(new_users) == 1
    assert new_users[0].email == "new@example.com"
    assert new_users[0].account_verified is False
    assert created_codes == [("account_verify", "email", "new@example.com")]
    assert sent_codes == [("email", "new@example.com", "123456")]
    assert saved


def test_login_page_success_creates_session_and_redirects(monkeypatch):
    alice = make_user()
    events = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "find_user_by_login", lambda login_value: (alice, "email", "alice@example.com"))
    monkeypatch.setattr(app, "is_login_temporarily_locked", lambda email: (False, 0))
    monkeypatch.setattr(app, "verify_user_password", lambda user, password: password == "correct-password")
    monkeypatch.setattr(app, "is_account_verified", lambda user: True)
    monkeypatch.setattr(app, "user_requires_login_2fa", lambda user: False)
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)
    monkeypatch.setattr(app, "bind_session_to_user", lambda user: None)
    monkeypatch.setattr(app, "record_trusted_device_seen", lambda user: None)
    monkeypatch.setattr(app, "send_login_alert", lambda user: None)
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": events.append((event_type, email, details)))

    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/login",
        data={
            "csrf_token": "token-1",
            "login": "alice@example.com",
            "password": "correct-password",
        },
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/onboarding/alice@example.com")
    with client.session_transaction() as session:
        assert session["user_email"] == "alice@example.com"
        assert session["csrf_token"] == "token-1"
    assert ("login_success", "alice@example.com", "2FA not required") in events


def test_verify_account_success_marks_account_and_starts_session(monkeypatch):
    alice = make_user()
    marked = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "find_user_by_contact", lambda contact_type, contact_value: alice)
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: code == "123456")
    monkeypatch.setattr(app, "mark_account_verified", lambda user, contact_type="email": marked.append((user.email, contact_type)))
    monkeypatch.setattr(app, "bind_session_to_user", lambda user: None)
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)

    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/verify_account?contact_type=email&contact_value=alice@example.com",
        data={
            "csrf_token": "token-1",
            "code": "123456",
        },
    )

    assert response.status_code == 303
    assert response.headers["Location"].endswith("/onboarding/alice@example.com")
    assert marked == [("alice@example.com", "email")]
    with client.session_transaction() as session:
        assert session["user_email"] == "alice@example.com"


def test_verify_account_page_uses_session_language_without_russian_mixing(monkeypatch):
    monkeypatch.setattr(app, "find_user_by_contact", lambda contact_type, contact_value: None)
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: False)
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"
        session["language"] = "tr"

    response = client.post(
        "/verify_account?contact_type=email&contact_value=alice@example.com",
        data={
            "csrf_token": "token-1",
            "code": "000000",
        },
        headers={"Accept-Language": "ru-RU"},
    )

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "Hesap doğrulama".encode("utf-8") in response.data
    assert "Kod geçersiz veya süresi dolmuş.".encode("utf-8") in response.data
    assert "Подтверждение аккаунта".encode("utf-8") not in response.data
    assert "Неверный или просроченный код".encode("utf-8") not in response.data
