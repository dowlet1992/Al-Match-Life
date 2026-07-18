from datetime import datetime, timedelta

from backend.services import stories_privacy_service


def test_story_active_window_is_24_hours():
    now = datetime(2026, 7, 17, 12, 0, 0)

    assert stories_privacy_service.is_story_active({
        "created_at": (now - timedelta(hours=23, minutes=59)).strftime("%Y-%m-%d %H:%M:%S")
    }, now=now) is True
    assert stories_privacy_service.is_story_active({
        "created_at": (now - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
    }, now=now) is False
    assert stories_privacy_service.is_story_active({"created_at": "bad"}) is False


def test_hide_and_show_stories_updates_relationship_map():
    data, changed = stories_privacy_service.hide_stories_from_user(
        "Alice@Example.com",
        "Bob@Example.com",
        {"hidden_stories": {}},
    )

    assert changed is True
    assert data == {"hidden_stories": {"alice@example.com": ["bob@example.com"]}}
    assert stories_privacy_service.has_hidden_stories_from("alice@example.com", "bob@example.com", data) is True

    data, changed = stories_privacy_service.show_stories_from_user(
        "alice@example.com",
        "bob@example.com",
        data,
    )

    assert changed is True
    assert data == {"hidden_stories": {"alice@example.com": []}}


def test_can_view_user_stories_respects_visibility_block_and_friendship():
    assert stories_privacy_service.can_view_user_stories(
        "alice@example.com",
        "bob@example.com",
        {"story_visibility": "everyone"},
        {"hidden_stories": {}},
        lambda one, two: False,
        lambda one, two: False,
    ) is True

    assert stories_privacy_service.can_view_user_stories(
        "alice@example.com",
        "bob@example.com",
        {"story_visibility": "friends"},
        {"hidden_stories": {}},
        lambda one, two: False,
        lambda one, two: False,
    ) is False

    assert stories_privacy_service.can_view_user_stories(
        "alice@example.com",
        "bob@example.com",
        {"story_visibility": "friends"},
        {"hidden_stories": {}},
        lambda one, two: False,
        lambda one, two: True,
    ) is True

    assert stories_privacy_service.can_view_user_stories(
        "alice@example.com",
        "bob@example.com",
        {"story_visibility": "everyone"},
        {"hidden_stories": {}},
        lambda one, two: one == "bob@example.com" and two == "alice@example.com",
        lambda one, two: True,
    ) is False

    assert stories_privacy_service.can_view_user_stories(
        "alice@example.com",
        "bob@example.com",
        {"story_visibility": "everyone"},
        {"hidden_stories": {"alice@example.com": ["bob@example.com"]}},
        lambda one, two: False,
        lambda one, two: True,
    ) is False
