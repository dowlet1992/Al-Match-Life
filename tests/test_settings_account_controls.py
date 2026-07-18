import app
import json
from backend.models import User


def make_user(email="alice@example.com", password="old-password-123"):
    user = User("Alice", 28, email, password, "Germany", "Bio", "Founder", "Partners", ["English"], ["Build"], ["AI"], ["Sales"])
    app.set_user_password(user, password)
    return user


def login(client, email="alice@example.com"):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"
        session["language"] = "en"


def install_settings_store(monkeypatch, initial=None):
    store = initial or {}

    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: dict(store.get(app.normalize_email(email), {})))
    monkeypatch.setattr(app, "repository_save_user_ai_settings", lambda email, settings: store.update({app.normalize_email(email): dict(settings)}))
    return store


def test_email_change_requires_code_and_updates_session(monkeypatch):
    user = make_user()
    settings_store = install_settings_store(monkeypatch, {"alice@example.com": {"profile_visibility": "friends"}})
    saved_users = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: saved_users.append(list(users)))
    monkeypatch.setattr(app, "create_verification_code", lambda *args: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda *args: True)
    monkeypatch.setattr(app, "verify_contact_code", lambda *args: args[-1] == "123456")
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "save_account_deletion_snapshot", lambda email: f"backups/deleted_accounts/{email}.json")

    client = app.app.test_client()
    login(client)

    send_response = client.post(
        "/settings/alice@example.com/email_phone",
        data={
            "csrf_token": "token-1",
            "action": "send",
            "current_password": "old-password-123",
            "new_email": "new@example.com",
        },
    )
    confirm_response = client.post(
        "/settings/alice@example.com/email_phone",
        data={"csrf_token": "token-1", "action": "confirm", "confirmation_code": "123456"},
    )

    assert send_response.status_code == 200
    assert b"Confirmation code sent." in send_response.data
    assert confirm_response.status_code == 200
    assert b"Contact details updated." in confirm_response.data
    assert user.email == "new@example.com"
    assert settings_store["new@example.com"]["profile_visibility"] == "friends"
    assert saved_users
    with client.session_transaction() as session:
        assert session["user_email"] == "new@example.com"


def test_trusted_devices_adds_and_removes_current_device(monkeypatch):
    user = make_user()
    settings_store = install_settings_store(monkeypatch)

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login(client)

    add_response = client.post(
        "/settings/alice@example.com/trusted_devices",
        data={"csrf_token": "token-1", "action": "trust"},
        headers={"User-Agent": "AI Match Test Browser"},
    )
    device_id = settings_store["alice@example.com"]["trusted_devices"][0]["id"]
    assert settings_store["alice@example.com"]["trusted_devices"][0]["last_seen_at"]
    remove_response = client.post(
        "/settings/alice@example.com/trusted_devices",
        data={"csrf_token": "token-1", "action": "remove", "device_id": device_id},
        headers={"User-Agent": "AI Match Test Browser"},
    )

    assert add_response.status_code == 200
    assert b"Device added to trusted devices." in add_response.data
    assert remove_response.status_code == 200
    assert settings_store["alice@example.com"]["trusted_devices"] == []


def test_login_updates_last_seen_for_trusted_device(monkeypatch):
    user = make_user()
    settings_store = install_settings_store(monkeypatch, {
        "alice@example.com": {
            "trusted_devices": [
                {
                    "id": "device-1",
                    "label": "Old browser",
                    "ip": "old-ip",
                    "trusted_at": "2026-07-16 10:00:00",
                    "last_seen_at": "2026-07-16 10:00:00",
                }
            ]
        }
    })

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "current_device_fingerprint", lambda: "device-1")
    monkeypatch.setattr(app, "clear_login_attempts", lambda email: None)
    monkeypatch.setattr(app, "send_login_alert", lambda user: None)
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"

    response = client.post(
        "/login",
        data={"csrf_token": "token-1", "login": "alice@example.com", "password": "old-password-123"},
        headers={"User-Agent": "Fresh trusted browser", "X-Forwarded-For": "203.0.113.7"},
    )

    trusted_device = settings_store["alice@example.com"]["trusted_devices"][0]
    assert response.status_code == 303
    assert trusted_device["label"] == "Fresh trusted browser"
    assert trusted_device["ip"] == "203.0.113.7"
    assert trusted_device["last_seen_at"] != "2026-07-16 10:00:00"


def test_delete_account_requires_phrase_code_and_removes_core_data(monkeypatch):
    user = make_user()
    other = make_user("bob@example.com")
    saved_users = []
    saved_feed = []
    saved_messages = []
    saved_notifications = []
    saved_social = []
    saved_blocks = []
    saved_restrictions = []
    saved_hidden_stories = []
    saved_reports = []
    saved_stories = []
    saved_proofs = []
    saved_ai_core_memory = []
    saved_ai_feed_learning = []
    saved_presence = []
    saved_typing = []
    saved_call_signals = []
    settings_store = install_settings_store(monkeypatch, {"alice@example.com": {"profile_visibility": "private"}})

    monkeypatch.setattr(app, "users", [user, other])
    monkeypatch.setattr(app, "save_users_to_json", lambda users: saved_users.append(list(users)))
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": [{"email": "alice@example.com"}, {"email": "bob@example.com"}]})
    monkeypatch.setattr(app, "save_feed", lambda data: saved_feed.append(data))
    monkeypatch.setattr(app, "load_messages", lambda: [{"from": "alice@example.com", "to": "bob@example.com"}, {"from": "bob@example.com", "to": "carol@example.com"}])
    monkeypatch.setattr(app, "save_messages", lambda data: saved_messages.append(data))
    monkeypatch.setattr(app, "load_notifications", lambda: [{"email": "alice@example.com"}, {"email": "bob@example.com"}])
    monkeypatch.setattr(app, "save_notifications", lambda data: saved_notifications.append(data))
    monkeypatch.setattr(app, "load_social", lambda: {
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}, {"user": "bob@example.com", "friend": "carol@example.com"}],
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}, {"follower": "bob@example.com", "following": "carol@example.com"}],
        "friend_requests": [{"from": "bob@example.com", "to": "alice@example.com"}, {"from": "bob@example.com", "to": "carol@example.com"}],
    })
    monkeypatch.setattr(app, "save_social", lambda data: saved_social.append(data))
    monkeypatch.setattr(app, "load_blocks", lambda: {"blocks": {"alice@example.com": ["bob@example.com"], "bob@example.com": ["alice@example.com", "carol@example.com"]}})
    monkeypatch.setattr(app, "save_blocks", lambda data: saved_blocks.append(data))
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"alice@example.com": ["bob@example.com"], "bob@example.com": ["alice@example.com", "carol@example.com"]}})
    monkeypatch.setattr(app, "save_restrictions", lambda data: saved_restrictions.append(data))
    monkeypatch.setattr(app, "load_hidden_stories", lambda: {"hidden_stories": {"alice@example.com": ["bob@example.com"], "bob@example.com": ["alice@example.com", "carol@example.com"]}})
    monkeypatch.setattr(app, "save_hidden_stories", lambda data: saved_hidden_stories.append(data))
    monkeypatch.setattr(app, "load_reports", lambda: {"reports": [{"reporter_email": "alice@example.com", "target_email": "bob@example.com"}, {"reporter_email": "bob@example.com", "target_email": "carol@example.com"}]})
    monkeypatch.setattr(app, "save_reports", lambda data: saved_reports.append(data))
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": [{"email": "alice@example.com"}, {"email": "bob@example.com"}]})
    monkeypatch.setattr(app, "save_stories", lambda data: saved_stories.append(data))
    monkeypatch.setattr(app, "load_proofs", lambda: {"proofs": [{"email": "alice@example.com"}, {"email": "bob@example.com"}]})
    monkeypatch.setattr(app, "save_proofs", lambda data: saved_proofs.append(data))
    monkeypatch.setattr(app, "load_ai_core_memory", lambda: {"alice@example.com": [{"answer": "x"}], "bob@example.com": [{"answer": "y"}]})
    monkeypatch.setattr(app, "save_ai_core_memory", lambda data: saved_ai_core_memory.append(data))
    monkeypatch.setattr(app, "load_ai_feed_learning", lambda: {"alice@example.com": {"actions": []}, "bob@example.com": {"actions": []}})
    monkeypatch.setattr(app, "save_ai_feed_learning", lambda data: saved_ai_feed_learning.append(data))
    monkeypatch.setattr(app, "load_presence_status", lambda: {"alice@example.com": {"online": True}, "bob@example.com": {"online": False}})
    monkeypatch.setattr(app, "save_presence_status", lambda data: saved_presence.append(data))
    monkeypatch.setattr(app, "load_typing_status", lambda: {"alice@example.com__bob@example.com": {"is_typing": True}, "bob@example.com__carol@example.com": {"is_typing": False}})
    monkeypatch.setattr(app, "save_typing_status", lambda data: saved_typing.append(data))
    monkeypatch.setattr(app, "load_call_signals", lambda: {"alice@example.com__bob@example.com": {"status": "ringing"}, "bob@example.com__carol@example.com": {"status": "ended"}})
    monkeypatch.setattr(app, "save_call_signals", lambda data: saved_call_signals.append(data))
    monkeypatch.setattr(app, "create_verification_code", lambda *args: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda *args: True)
    monkeypatch.setattr(app, "verify_contact_code", lambda *args: args[-1] == "123456")
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)

    client = app.app.test_client()
    login(client)

    send_response = client.post(
        "/settings/alice@example.com/delete",
        data={"csrf_token": "token-1", "action": "send", "current_password": "old-password-123"},
    )
    bad_phrase_response = client.post(
        "/settings/alice@example.com/delete",
        data={"csrf_token": "token-1", "action": "confirm", "confirmation_code": "123456", "confirmation_phrase": "delete"},
    )
    confirm_response = client.post(
        "/settings/alice@example.com/delete",
        data={"csrf_token": "token-1", "action": "confirm", "confirmation_code": "123456", "confirmation_phrase": "DELETE MY ACCOUNT"},
    )

    assert send_response.status_code == 200
    assert b"Deletion code sent." in send_response.data
    assert b"Confirmation phrase is incorrect." in bad_phrase_response.data
    assert confirm_response.status_code == 200
    assert b"Account deleted." in confirm_response.data
    assert [saved_user.email for saved_user in saved_users[-1]] == ["bob@example.com"]
    assert saved_feed[-1]["posts"] == [{"email": "bob@example.com"}]
    assert saved_messages[-1] == [{"from": "bob@example.com", "to": "carol@example.com"}]
    assert saved_notifications[-1] == [{"email": "bob@example.com"}]
    assert settings_store["alice@example.com"] == {}
    assert saved_social[-1] == {
        "friends": [{"user": "bob@example.com", "friend": "carol@example.com"}],
        "follows": [{"follower": "bob@example.com", "following": "carol@example.com"}],
        "friend_requests": [{"from": "bob@example.com", "to": "carol@example.com"}],
    }
    assert saved_blocks[-1] == {"blocks": {"bob@example.com": ["carol@example.com"]}}
    assert saved_restrictions[-1] == {"restrictions": {"bob@example.com": ["carol@example.com"]}}
    assert saved_hidden_stories[-1] == {"hidden_stories": {"bob@example.com": ["carol@example.com"]}}
    assert saved_reports[-1]["reports"] == [{"reporter_email": "bob@example.com", "target_email": "carol@example.com"}]
    assert saved_stories[-1]["stories"] == [{"email": "bob@example.com"}]
    assert saved_proofs[-1]["proofs"] == [{"email": "bob@example.com"}]
    assert saved_ai_core_memory[-1] == {"bob@example.com": [{"answer": "y"}]}
    assert saved_ai_feed_learning[-1] == {"bob@example.com": {"actions": []}}
    assert saved_presence[-1] == {"bob@example.com": {"online": False}}
    assert saved_typing[-1] == {"bob@example.com__carol@example.com": {"is_typing": False}}
    assert saved_call_signals[-1] == {"bob@example.com__carol@example.com": {"status": "ended"}}


def test_account_deletion_snapshot_is_written_before_cleanup(monkeypatch, tmp_path):
    user = make_user()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: {"profile_visibility": "private"})
    monkeypatch.setattr(app, "load_feed", lambda: {"posts": [{"email": "alice@example.com", "text": "Keep snapshot"}]})
    monkeypatch.setattr(app, "load_messages", lambda: [{"from": "alice@example.com", "to": "bob@example.com", "text": "Hi"}])
    monkeypatch.setattr(app, "load_notifications", lambda: [{"email": "alice@example.com", "text": "Notice"}])
    monkeypatch.setattr(app, "load_social", lambda: {
        "friends": [
            {"user": "alice@example.com", "friend": "bob@example.com"},
            {"user": "bob@example.com", "friend": "carol@example.com"},
        ],
        "follows": [
            {"follower": "alice@example.com", "following": "bob@example.com"},
            {"follower": "bob@example.com", "following": "carol@example.com"},
        ],
        "friend_requests": [
            {"from": "bob@example.com", "to": "alice@example.com"},
            {"from": "bob@example.com", "to": "carol@example.com"},
        ],
    })
    monkeypatch.setattr(app, "load_blocks", lambda: {
        "blocks": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com", "carol@example.com"],
            "carol@example.com": ["bob@example.com"],
        }
    })
    monkeypatch.setattr(app, "load_restrictions", lambda: {
        "restrictions": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com", "carol@example.com"],
        }
    })
    monkeypatch.setattr(app, "load_hidden_stories", lambda: {
        "hidden_stories": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com", "carol@example.com"],
        }
    })
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": [{"email": "alice@example.com", "text": "Story"}]})
    monkeypatch.setattr(app, "load_proofs", lambda: {"proofs": [{"email": "alice@example.com", "type": "identity"}]})
    monkeypatch.setattr(app, "load_reports", lambda: {"reports": []})
    monkeypatch.setattr(app, "load_ai_core_memory", lambda: {"alice@example.com": [{"answer": "AI memory"}]})
    monkeypatch.setattr(app, "load_ai_feed_learning", lambda: {"alice@example.com": {"actions": ["view"]}})

    path = app.save_account_deletion_snapshot("alice@example.com")

    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)

    assert path.startswith("backups/deleted_accounts/alice_at_example_com_")
    assert data["snapshot_type"] == "account_deletion"
    assert data["account"]["email"] == "alice@example.com"
    assert "password" not in data["account"]
    assert data["posts"][0]["text"] == "Keep snapshot"
    assert data["social"] == {
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}],
        "friend_requests": [{"from": "bob@example.com", "to": "alice@example.com"}],
    }
    assert data["safety"] == {
        "blocks": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com"],
        },
        "restrictions": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com"],
        },
        "hidden_stories": {
            "alice@example.com": ["bob@example.com"],
            "bob@example.com": ["alice@example.com"],
        },
    }
    assert data["settings"]["profile_visibility"] == "private"
    assert data["ai_core_memory"][0]["answer"] == "AI memory"
