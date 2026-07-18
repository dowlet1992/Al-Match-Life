from backend.services import notification_privacy_service


def test_notification_master_switch_blocks_everything():
    assert notification_privacy_service.allows_notification(
        {"notifications_enabled": False, "message_notifications": True},
        "message",
    ) is False


def test_notification_type_switches_are_respected():
    settings = {
        "notifications_enabled": True,
        "message_notifications": False,
        "friend_request_notifications": True,
        "match_notifications": False,
        "product_update_notifications": False,
        "login_alerts": True,
    }

    assert notification_privacy_service.allows_notification(settings, "message") is False
    assert notification_privacy_service.allows_notification(settings, "new_follower") is True
    assert notification_privacy_service.allows_notification(settings, "ai_match") is False
    assert notification_privacy_service.allows_notification(settings, "product_update") is False
    assert notification_privacy_service.allows_notification(settings, "login_alert") is True
    assert notification_privacy_service.allows_notification(settings, "unknown") is True


def test_restricted_sender_suppresses_notification():
    assert notification_privacy_service.allows_notification(
        {"notifications_enabled": True, "message_notifications": True},
        "message",
        from_email="alice@example.com",
        target_email="bob@example.com",
        is_restricted=lambda target, sender: target == "bob@example.com" and sender == "alice@example.com",
    ) is False
