from backend.services import profile_actions_service


def safe_text(value):
    return str(value or "").strip().replace("<", "&lt;").replace(">", "&gt;")


def test_render_profile_actions_for_own_profile():
    html = profile_actions_service.render_profile_actions({
        "is_own_profile": True,
        "owner_email": "alice@example.com",
        "viewer_email": "alice@example.com",
    }, safe_text)

    assert "/dashboard/alice@example.com" in html
    assert "/settings/alice@example.com" in html
    assert "Подписаться" not in html


def test_render_profile_actions_for_public_profile_follow_and_message():
    html = profile_actions_service.render_profile_actions({
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
    }, safe_text)

    assert "/follow/alice@example.com/bob@example.com" in html
    assert "/chat/alice@example.com/bob@example.com" in html
    assert "/hide_stories/alice@example.com/bob@example.com" in html
    assert "/restrict_user/alice@example.com/bob@example.com" in html
    assert "/block_user/alice@example.com/bob@example.com" in html


def test_render_profile_actions_for_following_restricted_and_hidden_stories():
    html = profile_actions_service.render_profile_actions({
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
    }, safe_text)

    assert "/unfollow/alice@example.com/bob@example.com" in html
    assert "/chat/alice@example.com/bob@example.com" in html
    assert "/show_stories/alice@example.com/bob@example.com" in html
    assert "/unrestrict_user/alice@example.com/bob@example.com" in html
    assert "/unblock_user/alice@example.com/bob@example.com" in html


def test_render_profile_actions_respects_message_permissions():
    closed_html = profile_actions_service.render_profile_actions({
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
    }, safe_text)
    verified_html = profile_actions_service.render_profile_actions({
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
    }, safe_text)

    assert "Сообщение закрыто" in closed_html
    assert "/chat/alice@example.com/bob@example.com" in verified_html


def test_render_profile_actions_uses_translation_bundle():
    html = profile_actions_service.render_profile_actions({
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
    }, safe_text, {
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

    assert "Takip et" in html
    assert "Hikayelerimi gizle" in html
    assert "Подписаться" not in html
    assert "Скрыть мои истории" not in html
