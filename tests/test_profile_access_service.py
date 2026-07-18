from backend.services import profile_access_service


def test_message_permission_status_respects_blocks_restrictions_and_settings():
    assert profile_access_service.message_permission_status(
        "alice@example.com",
        "bob@example.com",
        True,
        {"message_permission": "everyone"},
        lambda one, two: False,
        lambda one, two: False,
        lambda one, two: False,
    ) == (True, "", "")

    allowed, title, _ = profile_access_service.message_permission_status(
        "alice@example.com",
        "bob@example.com",
        True,
        {"message_permission": "friends"},
        lambda one, two: False,
        lambda one, two: False,
        lambda one, two: False,
    )
    assert allowed is False
    assert "Только друзья" in title

    allowed, title, _ = profile_access_service.message_permission_status(
        "alice@example.com",
        "bob@example.com",
        False,
        {"message_permission": "verified"},
        lambda one, two: False,
        lambda one, two: False,
        lambda one, two: True,
    )
    assert allowed is False
    assert "verified" in title

    allowed, title, _ = profile_access_service.message_permission_status(
        "alice@example.com",
        "bob@example.com",
        True,
        {"message_permission": "everyone"},
        lambda one, two: False,
        lambda one, two: one == "bob@example.com" and two == "alice@example.com",
        lambda one, two: True,
    )
    assert allowed is False
    assert title == "Сообщения недоступны"


def test_visible_last_seen_text_respects_owner_setting():
    formatter = lambda timestamp: "online"

    assert profile_access_service.visible_last_seen_text(
        "alice@example.com",
        "bob@example.com",
        {"show_online_status": False},
        123,
        formatter,
    ) == "статус скрыт"
    assert profile_access_service.visible_last_seen_text(
        "bob@example.com",
        "bob@example.com",
        {"show_online_status": False},
        123,
        formatter,
    ) == "online"


def test_profile_view_status_allows_own_and_public_profiles():
    assert profile_access_service.profile_view_status(
        "alice@example.com",
        "alice@example.com",
        {"profile_visibility": "private", "account_deactivated": True},
        lambda one, two: False,
        lambda one, two: False,
    )["status"] == "allowed"

    assert profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {"profile_visibility": "public"},
        lambda one, two: False,
        lambda one, two: False,
    ) == {
        "status": "allowed",
        "is_own_profile": False,
        "profile_visibility": "public",
    }


def test_profile_view_status_blocks_when_either_side_blocked():
    viewer_blocked_owner = profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {},
        lambda one, two: one == "alice@example.com" and two == "bob@example.com",
        lambda one, two: False,
    )
    owner_blocked_viewer = profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {},
        lambda one, two: one == "bob@example.com" and two == "alice@example.com",
        lambda one, two: False,
    )

    assert viewer_blocked_owner["status"] == "viewer_blocked_owner"
    assert owner_blocked_viewer["status"] == "owner_blocked_viewer"


def test_profile_view_status_respects_deactivated_private_and_friends_only():
    assert profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {"account_deactivated": True},
        lambda one, two: False,
        lambda one, two: False,
    )["status"] == "deactivated"

    assert profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {"profile_visibility": "private"},
        lambda one, two: False,
        lambda one, two: False,
    )["status"] == "private"

    friends_only = profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {"profile_visibility": "friends"},
        lambda one, two: False,
        lambda one, two: False,
    )
    friends_allowed = profile_access_service.profile_view_status(
        "alice@example.com",
        "bob@example.com",
        {"profile_visibility": "friends"},
        lambda one, two: False,
        lambda one, two: True,
    )

    assert friends_only["status"] == "friends_only"
    assert friends_allowed["status"] == "allowed"


def test_can_show_in_ai_recommendations_respects_privacy_and_relationships():
    assert profile_access_service.can_show_in_ai_recommendations(
        "alice@example.com",
        "bob@example.com",
        {"show_in_search": True, "recommend_my_profile": True},
        lambda one, two: False,
        lambda one, two: False,
    ) is True

    assert profile_access_service.can_show_in_ai_recommendations(
        "alice@example.com",
        "bob@example.com",
        {"show_in_search": False, "recommend_my_profile": True},
        lambda one, two: False,
        lambda one, two: False,
    ) is False

    assert profile_access_service.can_show_in_ai_recommendations(
        "alice@example.com",
        "bob@example.com",
        {"show_in_search": True, "recommend_my_profile": True},
        lambda one, two: one == "alice@example.com" and two == "bob@example.com",
        lambda one, two: False,
    ) is False
