from backend.services import profile_actions_service


def safe_text(value):
    return str(value or "").strip().replace("<", "&lt;").replace(">", "&gt;")


def test_render_profile_actions_for_own_profile():
    actions = profile_actions_service.build_profile_actions({
        "is_own_profile": True,
        "owner_email": "alice@example.com",
        "viewer_email": "alice@example.com",
    })

    assert [item["url"] for item in actions["primary"]] == [
        "/dashboard/alice@example.com",
        "/settings/alice@example.com",
    ]
    assert actions["menu"] == []


def test_render_profile_actions_for_public_profile_follow_and_message():
    actions = profile_actions_service.build_profile_actions({
        "are_friends": False,
        "has_hidden_stories": False,
        "is_own_profile": False,
        "is_restricted": False,
        "message_permission": "everyone",
        "owner_email": "bob@example.com",
        "viewer_blocked_user": False,
        "viewer_email": "alice@example.com",
        "viewer_follows_user": False,
        "viewer_verified": False,
    })
    urls = [item.get("url", "") for item in actions["primary"] + actions["menu"]]

    assert "/follow/alice@example.com/bob@example.com" in urls
    assert "/chat/alice@example.com/bob@example.com" in urls
    assert "/hide_stories/alice@example.com/bob@example.com" in urls
    assert "/restrict_user/alice@example.com/bob@example.com" in urls
    assert "/block_user/alice@example.com/bob@example.com" in urls


def test_profile_follow_action_prefers_stable_uuid_identifiers():
    actions = profile_actions_service.build_profile_actions({
        "is_own_profile": False,
        "owner_email": "bob@example.com",
        "owner_id": "22222222-2222-4222-8222-222222222222",
        "viewer_email": "alice@example.com",
        "viewer_id": "11111111-1111-4111-8111-111111111111",
        "viewer_follows_user": False,
        "message_permission": "everyone",
    })

    assert actions["primary"][0]["url"] == (
        "/follow/11111111-1111-4111-8111-111111111111/"
        "22222222-2222-4222-8222-222222222222"
    )


def test_render_profile_actions_for_following_restricted_and_hidden_stories():
    actions = profile_actions_service.build_profile_actions({
        "are_friends": True,
        "has_hidden_stories": True,
        "is_own_profile": False,
        "is_restricted": True,
        "message_permission": "friends",
        "owner_email": "bob@example.com",
        "viewer_blocked_user": True,
        "viewer_email": "alice@example.com",
        "viewer_follows_user": True,
        "viewer_verified": False,
    })
    urls = [item.get("url", "") for item in actions["primary"] + actions["menu"]]

    assert "/unfollow/alice@example.com/bob@example.com" in urls
    assert "/chat/alice@example.com/bob@example.com" in urls
    assert "/show_stories/alice@example.com/bob@example.com" in urls
    assert "/unrestrict_user/alice@example.com/bob@example.com" in urls
    assert "/unblock_user/alice@example.com/bob@example.com" in urls


def test_render_profile_actions_respects_message_permissions():
    closed = profile_actions_service.build_profile_actions({
        "are_friends": False,
        "has_hidden_stories": False,
        "is_own_profile": False,
        "is_restricted": False,
        "message_permission": "friends",
        "owner_email": "bob@example.com",
        "viewer_blocked_user": False,
        "viewer_email": "alice@example.com",
        "viewer_follows_user": False,
        "viewer_verified": False,
    })
    verified = profile_actions_service.build_profile_actions({
        "are_friends": False,
        "has_hidden_stories": False,
        "is_own_profile": False,
        "is_restricted": False,
        "message_permission": "verified",
        "owner_email": "bob@example.com",
        "viewer_blocked_user": False,
        "viewer_email": "alice@example.com",
        "viewer_follows_user": False,
        "viewer_verified": True,
    })

    assert closed["primary"][1]["kind"] == "disabled"
    assert verified["primary"][1]["url"] == "/chat/alice@example.com/bob@example.com"


def test_render_profile_actions_uses_translation_bundle():
    actions = profile_actions_service.build_profile_actions({
        "are_friends": False,
        "has_hidden_stories": False,
        "is_own_profile": False,
        "is_restricted": False,
        "message_permission": "everyone",
        "owner_email": "bob@example.com",
        "viewer_blocked_user": False,
        "viewer_email": "alice@example.com",
        "viewer_follows_user": False,
        "viewer_verified": False,
    }, {
        "follow": "Takip et",
        "message": "Mesaj",
        "hide_my_stories": "Hikayelerimi gizle",
        "restrict": "Kısıtla",
        "block": "Engelle",
        "more": "Daha fazla",
        "copy_link": "Bağlantıyı kopyala",
        "link_copied": "Bağlantı kopyalandı",
        "share_profile": "Profili paylaş",
        "report": "Şikayet et",
        "cancel": "İptal",
    })

    labels = [item["label"] for item in actions["primary"] + actions["menu"]]
    assert "Takip et" in labels
    assert "Hikayelerimi gizle" in labels
    assert "Подписаться" not in labels
    assert "Скрыть мои истории" not in labels
