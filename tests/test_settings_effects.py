import app
from backend.models import User


def test_social_notifications_respect_user_notification_settings(monkeypatch):
    stored_notifications = []

    monkeypatch.setattr(
        app,
        "normalize_user_ai_settings",
        lambda email: {
            "notifications_enabled": True,
            "friend_request_notifications": False,
            "message_notifications": True,
            "match_notifications": True,
            "product_update_notifications": False,
        },
    )
    monkeypatch.setattr(
        app,
        "add_notification",
        lambda email, text, notification_type, from_email: stored_notifications.append(
            {
                "email": email,
                "text": text,
                "type": notification_type,
                "from": from_email,
            }
        ),
    )

    app.create_social_notification("bob@example.com", "Alice followed you", "new_follower", "alice@example.com")

    assert stored_notifications == []


def test_notifications_are_suppressed_when_sender_is_restricted(monkeypatch):
    stored_notifications = []

    monkeypatch.setattr(
        app,
        "normalize_user_ai_settings",
        lambda email: {
            "notifications_enabled": True,
            "friend_request_notifications": True,
            "message_notifications": True,
            "match_notifications": True,
            "product_update_notifications": True,
        },
    )
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"bob@example.com": ["alice@example.com"]}})
    monkeypatch.setattr(
        app,
        "add_notification",
        lambda email, text, notification_type, from_email: stored_notifications.append(
            {
                "email": email,
                "text": text,
                "type": notification_type,
                "from": from_email,
            }
        ),
    )

    app.create_social_notification("bob@example.com", "Alice sent a message", "message", "alice@example.com")

    assert stored_notifications == []


def test_ai_feed_learning_respects_user_settings(monkeypatch):
    saved_learning = []

    monkeypatch.setattr(
        app,
        "normalize_user_ai_settings",
        lambda email: {
            "ai_feed_learning": False,
            "ai_activity_analysis": True,
        },
    )
    monkeypatch.setattr(app, "load_ai_feed_learning", lambda: {})
    monkeypatch.setattr(app, "save_ai_feed_learning", lambda data: saved_learning.append(data))

    app.record_ai_feed_signal(
        "alice@example.com",
        {"id": "post-1", "language": "en", "type": "News", "text": "AI update"},
        "view",
    )

    assert saved_learning == []
    assert app.calculate_ai_learning_boost(
        "alice@example.com",
        {"id": "post-1", "language": "en", "type": "News", "text": "AI update"},
        "en",
    ) == (0, [])


def test_profile_visibility_private_blocks_other_viewer(monkeypatch):
    viewer = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    target = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [viewer, target])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "profile_visibility": "private" if email == "bob@example.com" else "public",
        "message_permission": "everyone",
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/profile/bob@example.com?viewer=alice@example.com")

    assert response.status_code == 200
    assert "Профиль закрыт".encode("utf-8") in response.data


def test_story_visibility_blocks_direct_story_link(monkeypatch):
    viewer = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    owner = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [viewer, owner])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "story_visibility": "none" if email == "bob@example.com" else "friends",
    })
    monkeypatch.setattr(app, "load_stories", lambda: {
        "stories": [{
            "id": "story-1",
            "email": "bob@example.com",
            "media_url": "/static/story.jpg",
            "media_type": "image",
            "created_at": app.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "views": [],
        }]
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/story/alice@example.com/bob@example.com")

    assert response.status_code == 200
    assert "Story недоступна".encode("utf-8") in response.data
    assert "ограничил аудиторию".encode("utf-8") in response.data


def test_story_visibility_everyone_allows_direct_story_link(monkeypatch):
    viewer = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    owner = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    saved_stories = []

    monkeypatch.setattr(app, "users", [viewer, owner])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "story_visibility": "everyone" if email == "bob@example.com" else "friends",
    })
    monkeypatch.setattr(app, "load_stories", lambda: {
        "stories": [{
            "id": "story-1",
            "email": "bob@example.com",
            "media_url": "/static/story.jpg",
            "media_type": "image",
            "created_at": app.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "views": [],
        }]
    })
    monkeypatch.setattr(app, "save_stories", lambda data: saved_stories.append(data))

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/story/alice@example.com/bob@example.com")

    assert response.status_code == 200
    assert b"story-shell" in response.data
    assert saved_stories


def test_online_status_respects_visibility_setting(monkeypatch):
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "show_online_status": False if email == "bob@example.com" else True,
    })

    assert app.format_visible_last_seen("alice@example.com", "bob@example.com", app.datetime.now().timestamp()) == "статус скрыт"
    assert app.format_visible_last_seen("bob@example.com", "bob@example.com", app.datetime.now().timestamp()) == "🟢 онлайн"


def test_login_respects_user_two_factor_setting(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "secret123", "Germany", "", "", "", [], [], [], [])
    sent_codes = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "LOGIN_2FA_ENABLED", False)
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"two_factor_required": True})
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)
    monkeypatch.setattr(app, "create_verification_code", lambda purpose, contact_type, contact_value: "123456")
    monkeypatch.setattr(app, "send_verification_code", lambda contact_type, contact_value, code: sent_codes.append(code))

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"
        session["language"] = "en"

    response = client.post(
        "/login",
        data={
            "csrf_token": "token-1",
            "login": "alice@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 303
    assert "/verify_login_2fa" in response.headers["Location"]
    assert sent_codes == ["123456"]


def test_dashboard_respects_autoplay_video_setting(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"autoplay_video": False})
    monkeypatch.setattr(app, "load_feed", lambda: {
        "posts": [{
            "id": "post-1",
            "email": "alice@example.com",
            "type": "Видео",
            "text": "Demo video",
            "date": "2026-07-16",
            "media_items": [{"url": "/static/demo.mp4", "type": "video"}],
            "likes": [],
            "comments": [],
            "shares": [],
            "saves": [],
        }]
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/dashboard/alice@example.com")

    assert response.status_code == 200
    assert b"const feedAutoplayEnabled = false;" in response.data
    assert "Нажмите ▶".encode("utf-8") in response.data


def test_login_alerts_create_security_notification(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "secret123", "Germany", "", "", "", [], [], [], [])
    stored_notifications = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "LOGIN_2FA_ENABLED", False)
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "two_factor_required": False,
        "notifications_enabled": True,
        "login_alerts": True,
    })
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)
    monkeypatch.setattr(
        app,
        "add_notification",
        lambda email, text, notification_type, from_email: stored_notifications.append({
            "email": email,
            "text": text,
            "type": notification_type,
            "from": from_email,
        }),
    )

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"
        session["language"] = "en"

    response = client.post(
        "/login",
        data={
            "csrf_token": "token-1",
            "login": "alice@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 303
    assert stored_notifications
    assert stored_notifications[0]["type"] == "login_alert"
    assert "untrusted device" in stored_notifications[0]["text"].lower()


def test_login_alerts_use_standard_text_for_trusted_device(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "secret123", "Germany", "", "", "", [], [], [], [])
    stored_notifications = []

    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "LOGIN_2FA_ENABLED", False)
    monkeypatch.setattr(app, "current_device_fingerprint", lambda: "trusted-device")
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "two_factor_required": False,
        "notifications_enabled": True,
        "login_alerts": True,
    })
    monkeypatch.setattr(app, "repository_load_user_ai_settings", lambda email: {
        "trusted_devices": [{"id": "trusted-device", "label": "Known", "trusted_at": "2026-07-17 10:00:00"}]
    })
    monkeypatch.setattr(app, "repository_save_user_ai_settings", lambda email, settings: None)
    monkeypatch.setattr(app, "save_users_to_json", lambda users: None)
    monkeypatch.setattr(
        app,
        "add_notification",
        lambda email, text, notification_type, from_email: stored_notifications.append({
            "email": email,
            "text": text,
            "type": notification_type,
            "from": from_email,
        }),
    )

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["csrf_token"] = "token-1"

    response = client.post(
        "/login",
        data={
            "csrf_token": "token-1",
            "login": "alice@example.com",
            "password": "secret123",
        },
    )

    assert response.status_code == 303
    assert stored_notifications
    assert "untrusted device" not in stored_notifications[0]["text"].lower()


def test_content_filters_hide_sensitive_and_adult_posts(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    author = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [user, author])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "autoplay_video": True,
        "sensitive_content_filter": True,
        "adult_content_filter": True,
    })
    monkeypatch.setattr(app, "load_feed", lambda: {
        "posts": [
            {
                "id": "safe-post",
                "email": "bob@example.com",
                "type": "Новость",
                "text": "Useful business update",
                "date": "2026-07-16",
                "likes": [],
                "comments": [],
                "shares": [],
                "saves": [],
            },
            {
                "id": "adult-post",
                "email": "bob@example.com",
                "type": "Новость",
                "text": "adult content",
                "date": "2026-07-16",
                "content_rating": "adult",
                "likes": [],
                "comments": [],
                "shares": [],
                "saves": [],
            },
            {
                "id": "sensitive-post",
                "email": "bob@example.com",
                "type": "Новость",
                "text": "violent content",
                "date": "2026-07-16",
                "moderation_flags": ["sensitive"],
                "likes": [],
                "comments": [],
                "shares": [],
                "saves": [],
            },
        ]
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/dashboard/alice@example.com")

    assert response.status_code == 200
    assert b"Useful business update" in response.data
    assert b"adult content" not in response.data
    assert b"violent content" not in response.data


def test_matches_respect_ai_match_explanations_setting(monkeypatch):
    current_user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "Founder", "", [], ["Build"], ["AI"], ["Sales"])
    matched_user = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "Engineer", "", [], ["Build"], ["AI"], ["Python"])
    explain_calls = []

    monkeypatch.setattr(app, "users", [current_user, matched_user])
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [{"user": matched_user, "score": 88}])
    monkeypatch.setattr(app, "can_show_user_in_ai_recommendations", lambda current_email, candidate: True)
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"ai_match_explanations": False})
    monkeypatch.setattr(app, "explain_match", lambda current, matched: explain_calls.append((current, matched)) or ["Shared goals"])

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/matches/alice@example.com")

    assert response.status_code == 200
    assert explain_calls == []
    assert "Почему AI рекомендует".encode("utf-8") not in response.data


def test_profile_activity_status_hides_public_activity(monkeypatch):
    viewer = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    target = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [viewer, target])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "profile_visibility": "public",
        "message_permission": "everyone",
        "show_activity_status": False if email == "bob@example.com" else True,
    })
    monkeypatch.setattr(app, "load_feed", lambda: {
        "posts": [{
            "id": "post-1",
            "email": "bob@example.com",
            "type": "Новость",
            "text": "Hidden profile activity post",
            "date": "2026-07-16",
            "likes": [],
            "comments": [],
            "shares": [],
            "saves": [],
        }]
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/profile/bob@example.com?viewer=alice@example.com")

    assert response.status_code == 200
    assert "Активность скрыта".encode("utf-8") in response.data
    assert b"Hidden profile activity post" not in response.data


def test_dashboard_hides_restricted_feed_authors(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 31, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_notifications", lambda email: [])
    monkeypatch.setattr(app, "load_stories", lambda: {"stories": []})
    monkeypatch.setattr(app, "find_best_matches", lambda user, users: [])
    monkeypatch.setattr(app, "load_restrictions", lambda: {"restrictions": {"alice@example.com": ["bob@example.com"]}})
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "autoplay_video": True,
        "adult_content_filter": True,
        "sensitive_content_filter": True,
    })
    monkeypatch.setattr(app, "load_feed", lambda: {
        "posts": [
            {
                "id": "post-1",
                "email": "bob@example.com",
                "type": "Идея",
                "text": "Restricted feed post",
                "date": "2026-07-16",
                "likes": [],
                "comments": [],
                "shares": [],
                "saves": [],
            }
        ]
    })

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/dashboard/alice@example.com")

    assert response.status_code == 200
    assert b"Restricted feed post" not in response.data
