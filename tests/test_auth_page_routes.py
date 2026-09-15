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
    assert new_users[0].language == "ru"
    assert created_codes == [("account_verify", "email", "new@example.com")]
    assert sent_codes == [("email", "new@example.com", "123456")]
    assert saved


def test_web_registration_persists_browser_language(monkeypatch):
    new_users = []
    saved_languages = []
    monkeypatch.setattr(app, "users", new_users)
    monkeypatch.setattr(app, "save_users_to_json", lambda users_value: None)
    monkeypatch.setattr(
        app,
        "save_user_raw_settings",
        lambda email, settings: saved_languages.append((email, dict(settings))),
    )
    monkeypatch.setattr(app, "create_verification_code", lambda *args: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda *args: True)
    client = app.app.test_client()
    set_csrf(client)

    response = client.post(
        "/register",
        headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"},
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "email": "new@example.com",
            "password": "strongpass123",
            "name": "New User",
            "age": "30",
            "country": "Germany",
        },
    )

    assert response.status_code == 302
    assert new_users[0].language == "de"
    assert saved_languages[0][0] == "new@example.com"
    assert saved_languages[0][1]["interface_language"] == "de"


def test_register_rejects_invalid_age_without_creating_user(monkeypatch):
    new_users = []
    monkeypatch.setattr(app, "users", new_users)

    client = app.app.test_client()
    set_csrf(client)
    response = client.post(
        "/register",
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "email": "new@example.com",
            "password": "strongpass123",
            "name": "New User",
            "age": "not-a-number",
            "country": "Germany",
        },
    )

    assert response.status_code == 400
    assert new_users == []


def test_turkish_registration_and_login_errors_are_localized(monkeypatch):
    alice = make_user()
    alice.language = "tr"
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "find_user_by_login", lambda value: (alice, "email", alice.email))
    monkeypatch.setattr(app, "is_login_temporarily_locked", lambda email: (False, 0))
    monkeypatch.setattr(app, "verify_user_password", lambda user, password: False)
    monkeypatch.setattr(app, "register_failed_login_attempt", lambda email: None)
    client = app.app.test_client()
    set_csrf(client)

    registration_response = client.post(
        "/register", headers={"Accept-Language": "tr-TR"},
        data={"csrf_token": "token-1", "contact_type": "email", "email": "new@example.com", "password": "strongpass123", "name": "New User", "age": "invalid", "country": "Germany"},
    )
    login_response = client.post(
        "/login", headers={"Accept-Language": "en-US"},
        data={"csrf_token": "token-1", "login": alice.email, "password": "wrong"},
    )

    assert registration_response.status_code == 400
    assert "Yaş sayı olmalıdır.".encode() in registration_response.data
    assert login_response.status_code == 401
    assert "E-posta, telefon numarası veya şifre yanlış.".encode() in login_response.data


def test_register_rejects_oversized_profile_data(monkeypatch):
    new_users = []
    monkeypatch.setattr(app, "users", new_users)

    client = app.app.test_client()
    set_csrf(client)
    response = client.post(
        "/register",
        data={
            "csrf_token": "token-1",
            "contact_type": "email",
            "email": "new@example.com",
            "password": "strongpass123",
            "name": "New User",
            "age": "30",
            "country": "Germany",
            "bio": "x" * 501,
        },
    )

    assert response.status_code == 400
    assert new_users == []


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
        session["language"] = "de"

    response = client.post(
        "/verify_account?contact_type=email&contact_value=alice@example.com",
        data={
            "csrf_token": "token-1",
            "code": "000000",
        },
        headers={"Accept-Language": "ru-RU"},
    )

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["back"].encode() in response.data
    assert "Подтверждение аккаунта".encode("utf-8") not in response.data
    assert "Неверный или просроченный код".encode("utf-8") not in response.data
