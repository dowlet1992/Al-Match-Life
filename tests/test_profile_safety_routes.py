import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email, name):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def install_users(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    monkeypatch.setattr(app, "users", [alice, bob])
    return alice, bob


def test_block_profile_route_blocks_and_redirects(monkeypatch):
    install_users(monkeypatch)
    blocked = []
    events = []

    monkeypatch.setattr(app, "block_user_account", lambda blocker, blocked_email: blocked.append((blocker, blocked_email)))
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": events.append((event_type, email, details)))

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/block_user/alice@example.com/bob@example.com", data={"csrf_token": "token-1"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile/bob@example.com?viewer=alice@example.com")
    assert blocked == [("alice@example.com", "bob@example.com")]
    assert events == [("user_blocked", "alice@example.com", "Blocked bob@example.com")]


def test_block_profile_route_rejects_self_block(monkeypatch):
    install_users(monkeypatch)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post("/block_user/alice@example.com/alice@example.com", data={"csrf_token": "token-1"})

    assert response.status_code == 200
    assert "Нельзя заблокировать себя".encode("utf-8") in response.data


def test_profile_qr_route_renders_profile_url(monkeypatch):
    install_users(monkeypatch)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/profile_qr/alice@example.com/bob@example.com")

    assert response.status_code == 200
    assert "QR-код профиля".encode("utf-8") in response.data
    assert b"/profile/bob@example.com?viewer=alice@example.com" in response.data
    assert b"api.qrserver.com" in response.data


def test_report_user_route_get_and_post(monkeypatch):
    install_users(monkeypatch)
    reports = []
    events = []

    monkeypatch.setattr(app, "add_profile_report", lambda reporter, target, reason, details: reports.append((reporter, target, reason, details)))
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": events.append((event_type, email, details)))

    client = app.app.test_client()
    login(client, "alice@example.com")

    get_response = client.get("/report_user/alice@example.com/bob@example.com")
    post_response = client.post(
        "/report_user/alice@example.com/bob@example.com",
        data={
            "csrf_token": "token-1",
            "reason": "Спам",
            "details": "Bad profile",
        },
    )

    assert get_response.status_code == 200
    assert "Пожаловаться на профиль".encode("utf-8") in get_response.data
    assert post_response.status_code == 200
    assert "Жалоба отправлена".encode("utf-8") in post_response.data
    assert reports == [("alice@example.com", "bob@example.com", "Спам", "Bad profile")]
    assert events == [("user_reported", "alice@example.com", "Reported bob@example.com; reason=Спам")]


def test_restrict_and_story_visibility_routes_redirect(monkeypatch):
    install_users(monkeypatch)
    calls = []

    monkeypatch.setattr(app, "restrict_user_account", lambda viewer, target: calls.append(("restrict", viewer, target)))
    monkeypatch.setattr(app, "unrestrict_user_account", lambda viewer, target: calls.append(("unrestrict", viewer, target)))
    monkeypatch.setattr(app, "hide_stories_from_user", lambda viewer, target: calls.append(("hide", viewer, target)))
    monkeypatch.setattr(app, "show_stories_from_user", lambda viewer, target: calls.append(("show", viewer, target)))
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)

    client = app.app.test_client()
    login(client, "alice@example.com")

    for path in [
        "/restrict_user/alice@example.com/bob@example.com",
        "/unrestrict_user/alice@example.com/bob@example.com",
        "/hide_stories/alice@example.com/bob@example.com",
        "/show_stories/alice@example.com/bob@example.com",
    ]:
        response = client.post(path, data={"csrf_token": "token-1"})
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile/bob@example.com?viewer=alice@example.com")

    assert calls == [
        ("restrict", "alice@example.com", "bob@example.com"),
        ("unrestrict", "alice@example.com", "bob@example.com"),
        ("hide", "alice@example.com", "bob@example.com"),
        ("show", "alice@example.com", "bob@example.com"),
    ]
