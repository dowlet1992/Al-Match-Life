import app
from backend.models import User


def make_user(email="alice@example.com", password="old-password-123"):
    user = User("Alice", 28, email, password, "Germany", "", "", "", [], [], [], [])
    app.set_user_password(user, password)
    return user


def test_devices_page_shows_current_session(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: {})

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["login_time"] = "2026-07-16 12:00:00"

    response = client.get(
        "/settings/alice@example.com/devices",
        headers={"User-Agent": "AI Match Test Browser"},
    )

    assert response.status_code == 200
    assert b"alice@example.com" in response.data
    assert b"2026-07-16 12:00:00" in response.data
    assert b"AI Match Test Browser" in response.data
    assert "Статус доверия".encode("utf-8") in response.data


def test_logout_current_device_clears_session(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"

    response = client.post(
        "/settings/alice@example.com/devices/logout_current",
        data={"csrf_token": "token-1"},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    with client.session_transaction() as session:
        assert "user_email" not in session


def test_devices_page_rejects_other_users(monkeypatch):
    monkeypatch.setattr(app, "users", [
        User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], []),
        User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], []),
    ])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    assert client.get("/settings/bob@example.com/devices").status_code == 403


def test_devices_page_shows_recent_session_history(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: {})
    monkeypatch.setattr(app, "load_security_events", lambda: [
        {
            "time": "2026-07-17 09:00:00",
            "event": "login_success",
            "email": "alice@example.com",
            "ip": "127.0.0.1",
            "details": "2FA not required",
        },
        {
            "time": "2026-07-17 09:05:00",
            "event": "login_success",
            "email": "bob@example.com",
            "ip": "127.0.0.2",
            "details": "Other user",
        },
    ])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["language"] = "en"

    response = client.get("/settings/alice@example.com/devices")

    assert response.status_code == 200
    assert b"Recent session history" in response.data
    assert b"2FA not required" in response.data
    assert b"127.0.0.1" in response.data
    assert b"127.0.0.2" not in response.data


def test_logout_other_devices_requires_current_password(monkeypatch):
    user = make_user()
    settings_store = {"alice@example.com": {"session_version": 1}}

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: dict(settings_store.get(app.normalize_email(email), {})))
    monkeypatch.setattr(app, "repository_save_user_ai_settings", lambda email, settings: settings_store.update({app.normalize_email(email): dict(settings)}))
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"
        session["session_version"] = 1

    response = client.post(
        "/settings/alice@example.com/devices/logout_others",
        data={"csrf_token": "token-1", "current_password": "wrong-password"},
    )

    assert response.status_code == 303
    assert "other_devices_password_invalid" in response.headers["Location"]
    assert settings_store["alice@example.com"]["session_version"] == 1


def test_logout_other_devices_rotates_session_version_and_keeps_current_session(monkeypatch):
    user = make_user()
    settings_store = {
        "alice@example.com": {
            "session_version": 1,
            "trusted_devices": [
                {"id": "current-device", "label": "Current", "trusted_at": "2026-07-17 10:00:00"},
                {"id": "old-device", "label": "Old", "trusted_at": "2026-07-16 10:00:00"},
            ],
        }
    }

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "current_device_fingerprint", lambda: "current-device")
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: dict(settings_store.get(app.normalize_email(email), {})))
    monkeypatch.setattr(app, "repository_save_user_ai_settings", lambda email, settings: settings_store.update({app.normalize_email(email): dict(settings)}))
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"
        session["session_version"] = 1

    response = client.post(
        "/settings/alice@example.com/devices/logout_others",
        data={"csrf_token": "token-1", "current_password": "old-password-123"},
    )

    assert response.status_code == 303
    assert settings_store["alice@example.com"]["session_version"] == 2
    assert settings_store["alice@example.com"]["trusted_devices"] == [
        {"id": "current-device", "label": "Current", "trusted_at": "2026-07-17 10:00:00"}
    ]
    with client.session_transaction() as session:
        assert session["user_email"] == "alice@example.com"
        assert session["session_version"] == 2


def test_stale_session_is_rejected_after_session_version_rotation(monkeypatch):
    user = make_user()

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: {"session_version": 2})
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["session_version"] = 1

    response = client.get("/settings/alice@example.com/devices")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    with client.session_transaction() as session:
        assert "user_email" not in session


def test_logout_other_devices_with_2fa_sends_code_and_requires_valid_code(monkeypatch):
    user = make_user()
    sent_codes = []
    settings_store = {
        "alice@example.com": {
            "session_version": 1,
            "trusted_devices": [
                {"id": "current-device", "label": "Current", "trusted_at": "2026-07-17 10:00:00"},
                {"id": "old-device", "label": "Old", "trusted_at": "2026-07-16 10:00:00"},
            ],
        }
    }

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "current_device_fingerprint", lambda: "current-device")
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"two_factor_required": True})
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: dict(settings_store.get(app.normalize_email(email), {})))
    monkeypatch.setattr(app, "repository_save_user_ai_settings", lambda email, settings: settings_store.update({app.normalize_email(email): dict(settings)}))
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: sent_codes.append((contact_type, contact_value, code)) or True)
    monkeypatch.setattr(app, "verify_contact_code", lambda purpose, contact_type, contact_value, code: code == "123456")
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"
        session["csrf_token"] = "token-1"
        session["session_version"] = 1

    send_response = client.post(
        "/settings/alice@example.com/devices/logout_others",
        data={"csrf_token": "token-1", "action": "send_security_code", "current_password": "old-password-123"},
    )
    invalid_response = client.post(
        "/settings/alice@example.com/devices/logout_others",
        data={
            "csrf_token": "token-1",
            "action": "logout_others",
            "current_password": "old-password-123",
            "confirmation_code": "000000",
        },
    )

    assert send_response.status_code == 303
    assert "security_code_sent" in send_response.headers["Location"]
    assert sent_codes == [("email", "alice@example.com", "123456")]
    assert invalid_response.status_code == 303
    assert "security_code_invalid" in invalid_response.headers["Location"]
    assert settings_store["alice@example.com"]["session_version"] == 1

    valid_response = client.post(
        "/settings/alice@example.com/devices/logout_others",
        data={
            "csrf_token": "token-1",
            "action": "logout_others",
            "current_password": "old-password-123",
            "confirmation_code": "123456",
        },
    )

    assert valid_response.status_code == 303
    assert "other_devices_signed_out_success" in valid_response.headers["Location"]
    assert settings_store["alice@example.com"]["session_version"] == 2
    assert settings_store["alice@example.com"]["trusted_devices"] == [
        {"id": "current-device", "label": "Current", "trusted_at": "2026-07-17 10:00:00"}
    ]
