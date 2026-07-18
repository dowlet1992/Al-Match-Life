import app
from backend.models import User


def make_user(email="alice@example.com", password="old-password-123"):
    user = User("Alice", 28, email, password, "Germany", "Bio", "Founder", "Partners", ["English"], ["Build"], ["AI"], ["Sales"])
    app.set_user_password(user, password)
    return user


def install_settings_store(monkeypatch, initial=None):
    store = initial or {}

    def load_settings(email):
        return dict(store.get(app.normalize_email(email), {}))

    def save_settings(email, settings):
        store[app.normalize_email(email)] = dict(settings)

    monkeypatch.setattr(app, "repository_load_user_ai_settings", load_settings)
    monkeypatch.setattr(app, "repository_save_user_ai_settings", save_settings)
    return store


def login_session(client, email="alice@example.com", language="en"):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"
        session["language"] = language


def test_deactivate_account_page_requires_owner(monkeypatch):
    alice = make_user()
    bob = make_user("bob@example.com")

    monkeypatch.setattr(app, "users", [alice, bob])

    client = app.app.test_client()
    login_session(client)

    response = client.get("/settings/bob@example.com/deactivate")

    assert response.status_code == 403


def test_deactivate_account_rejects_wrong_password(monkeypatch):
    user = make_user()
    settings_store = install_settings_store(monkeypatch)

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login_session(client)

    response = client.post(
        "/settings/alice@example.com/deactivate",
        data={"csrf_token": "token-1", "current_password": "wrong-password"},
    )

    assert response.status_code == 200
    assert b"Current password is incorrect." in response.data
    assert settings_store.get("alice@example.com", {}).get("account_deactivated") is not True


def test_deactivate_account_sets_status_and_clears_session(monkeypatch):
    user = make_user()
    settings_store = install_settings_store(monkeypatch)
    events = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: events.append(args))

    client = app.app.test_client()
    login_session(client)

    response = client.post(
        "/settings/alice@example.com/deactivate",
        data={"csrf_token": "token-1", "current_password": "old-password-123"},
    )

    assert response.status_code == 200
    assert b"Account deactivated. Sign in again to restore access." in response.data
    assert settings_store["alice@example.com"]["account_deactivated"] is True
    assert events[-1][0] == "account_deactivated"
    with client.session_transaction() as session:
        assert "user_email" not in session


def test_deactivated_account_is_hidden_from_search_and_matches(monkeypatch):
    alice = make_user()
    bob = make_user("bob@example.com")
    settings_store = install_settings_store(
        monkeypatch,
        {"bob@example.com": {"account_deactivated": True, "show_in_search": True, "recommend_my_profile": True}},
    )

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_user_privacy", lambda email: {"show_in_search": True, "vip_mode": False})
    monkeypatch.setattr(app, "is_blocked", lambda *args: False)
    monkeypatch.setattr(app, "is_restricted", lambda *args: False)
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [{"user": bob, "score": 92}])

    client = app.app.test_client()
    login_session(client)

    search_response = client.post(
        "/search/alice@example.com",
        data={"csrf_token": "token-1", "keyword": "Founder"},
    )
    matches_response = client.get("/matches/alice@example.com")

    assert search_response.status_code == 200
    assert b"bob@example.com" not in search_response.data
    assert matches_response.status_code == 200
    assert b"bob@example.com" not in matches_response.data
    assert settings_store["bob@example.com"]["account_deactivated"] is True


def test_login_reactivates_deactivated_account(monkeypatch):
    user = make_user()
    settings_store = install_settings_store(monkeypatch, {"alice@example.com": {"account_deactivated": True}})
    events = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)
    monkeypatch.setattr(app, "send_login_alert", lambda user: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: events.append(args))

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"

    response = client.post(
        "/login",
        data={"csrf_token": "token-1", "login": "alice@example.com", "password": "old-password-123"},
    )

    assert response.status_code == 303
    assert settings_store["alice@example.com"]["account_deactivated"] is False
    assert any(event[0] == "account_reactivated" for event in events)
