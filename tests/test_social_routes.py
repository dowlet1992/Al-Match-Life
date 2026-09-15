import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "social-csrf"


def make_user(name, email):
    return User(name, 28, email, "hashed", "Germany", "", "Engineer", "", [], [], [], [])


def test_followers_page_deduplicates_and_escapes_people(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("<script>alert(1)</script>", "bob@example.com")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_followers", lambda email: [bob.email, bob.email, "missing@example.com"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/followers/{alice.id}")

    assert response.status_code == 200
    assert response.data.count(f"/profile/{bob.id}".encode()) == 1
    assert b"/profile/bob@example.com" not in response.data
    assert b"<script>alert(1)</script>" not in response.data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in response.data


def test_friend_requests_page_renders_csrf_actions(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_friend_requests", lambda email: [{"from": bob.email}])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/friend_requests/{alice.id}")

    assert response.status_code == 200
    assert f"/profile/{bob.id}".encode() in response.data
    assert b"/profile/bob@example.com" not in response.data
    assert f"/accept_friend_request/{alice.id}/{bob.id}".encode() in response.data
    assert f"/decline_friend_request/{alice.id}/{bob.id}".encode() in response.data
    assert b'value="social-csrf"' in response.data


def test_social_mutation_rejects_viewer_email_different_from_session(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    charlie = make_user("Charlie", "charlie@example.com")
    calls = []
    monkeypatch.setattr(app, "users", [alice, bob, charlie])
    monkeypatch.setattr(app, "follow_user", lambda viewer, profile: calls.append((viewer, profile)) or True)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/follow/{bob.email}/{charlie.email}",
        data={"csrf_token": "social-csrf"},
    )

    assert response.status_code == 403
    assert calls == []


def test_friend_requests_are_private_to_the_authenticated_owner(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/friend_requests/{bob.id}")

    assert response.status_code == 403


def test_legacy_friend_requests_email_url_remains_compatible(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_friend_requests", lambda email: [])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/friend_requests/{alice.email}")

    assert response.status_code == 200


def test_other_users_followers_keep_viewer_navigation_identity(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    charlie = make_user("Charlie", "charlie@example.com")
    monkeypatch.setattr(app, "users", [alice, bob, charlie])
    monkeypatch.setattr(app, "get_followers", lambda email: [charlie.email])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/followers/{bob.id}")

    assert response.status_code == 200
    assert f'/messages/{alice.email}'.encode() in response.data
    assert f'/messages/{bob.email}'.encode() not in response.data
    assert f'/profile/{bob.id}?viewer={alice.email}'.encode() in response.data
    assert b"Bob" in response.data


def test_legacy_email_social_list_url_remains_compatible(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_followers", lambda email: [])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/followers/{alice.email}")

    assert response.status_code == 200


def test_follow_fetch_returns_compact_state_for_in_place_update(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "follow_user", lambda viewer, profile: True)
    monkeypatch.setattr(app, "count_followers", lambda email: 12)
    monkeypatch.setattr(app, "create_social_notification", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/follow/{alice.email}/{bob.email}",
        data={"csrf_token": "social-csrf"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "is_following": True,
        "followers_count": 12,
        "next_action": f"/unfollow/{alice.id}/{bob.id}",
        "label": "Подписки",
    }


def test_follow_notification_uses_recipient_language(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    bob.language = "de"
    notifications = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "follow_user", lambda viewer, profile: True)
    monkeypatch.setattr(app, "create_social_notification", lambda *args: notifications.append(args))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/follow/{alice.id}/{bob.id}",
        data={"csrf_token": "social-csrf"},
    )

    assert response.status_code == 302
    assert notifications[0][0] == bob.email
    assert notifications[0][1] == "Alice folgt Ihnen jetzt."


def test_follow_notification_and_social_list_use_turkish(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    alice.language = "tr"
    bob.language = "tr"
    notifications = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "follow_user", lambda viewer, profile: True)
    monkeypatch.setattr(app, "create_social_notification", lambda *args: notifications.append(args))
    monkeypatch.setattr(app, "get_followers", lambda email: [])
    client = app.app.test_client()
    login(client, alice.email)

    follow_response = client.post(
        f"/follow/{alice.id}/{bob.id}", data={"csrf_token": "social-csrf"}
    )
    list_response = client.get(f"/followers/{alice.id}")

    assert follow_response.status_code == 302
    assert notifications[0][1] == "Alice sizi takip etmeye başladı."
    assert list_response.status_code == 200
    assert "Takipçiler".encode() in list_response.data
    assert "Liste henüz boş.".encode() in list_response.data


def test_blocked_social_action_uses_viewer_language(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    alice.language = "de"
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "is_blocked", lambda one, two: True)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/follow/{alice.id}/{bob.id}",
        data={"csrf_token": "social-csrf"},
    )

    assert response.status_code == 200
    assert "Aktion nicht verfügbar".encode() in response.data
    assert "Das Folgen ist nicht möglich".encode() in response.data
    assert "Действие недоступно".encode() not in response.data


def test_blocked_social_action_uses_turkish(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    alice.language = "tr"
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "is_blocked", lambda one, two: True)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/follow/{alice.id}/{bob.id}", data={"csrf_token": "social-csrf"}
    )

    assert response.status_code == 200
    assert "İşlem kullanılamıyor".encode() in response.data
    assert "takip edilemiyor".encode() in response.data


def test_accept_friend_request_fetch_returns_localized_state(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "accept_friend_request", lambda viewer, profile: True)
    monkeypatch.setattr(app, "create_social_notification", lambda *args: None)
    monkeypatch.setattr(app, "update_friend_request_notification_status", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/accept_friend_request/{alice.email}/{bob.email}",
        data={"csrf_token": "social-csrf"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "accepted"
    assert payload["label"] == "Принято"
    assert payload["profile_id"] == bob.id


def test_decline_missing_friend_request_does_not_create_false_notification(monkeypatch):
    alice = make_user("Alice", "alice@example.com")
    bob = make_user("Bob", "bob@example.com")
    notifications = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "decline_friend_request", lambda viewer, profile: False)
    monkeypatch.setattr(app, "create_social_notification", lambda *args: notifications.append(args))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/decline_friend_request/{alice.email}/{bob.email}",
        data={"csrf_token": "social-csrf"},
        headers={"X-Requested-With": "fetch", "Accept": "application/json"},
    )

    assert response.status_code == 409
    assert response.get_json() == {"ok": False, "error": "friend_request_not_found"}
    assert notifications == []
