MESSAGE_NOTIFICATION_TYPES = {"message", "direct_message", "chat"}
SOCIAL_NOTIFICATION_TYPES = {"friend_request", "friend_request_accepted", "friend_request_declined", "new_follower", "social"}
MATCH_NOTIFICATION_TYPES = {"match", "ai_match", "ai_recommendation", "radar"}
PRODUCT_NOTIFICATION_TYPES = {"product_update", "announcement"}
SECURITY_NOTIFICATION_TYPES = {"login_alert", "security"}


def normalize_email(value):
    return str(value or "").strip().lower()


def clean_type(value):
    return str(value or "").strip().lower()


def allows_notification(settings, notification_type="system", from_email="", target_email="", is_restricted=None):
    settings = settings if isinstance(settings, dict) else {}
    notification_type = clean_type(notification_type)
    normalized_target_email = normalize_email(target_email)
    normalized_from_email = normalize_email(from_email)

    if settings.get("notifications_enabled") is False:
        return False

    if (
        normalized_target_email
        and normalized_from_email
        and callable(is_restricted)
        and is_restricted(normalized_target_email, normalized_from_email)
    ):
        return False

    if notification_type in MESSAGE_NOTIFICATION_TYPES:
        return settings.get("message_notifications", True) is True

    if notification_type in SOCIAL_NOTIFICATION_TYPES:
        return settings.get("friend_request_notifications", True) is True

    if notification_type in MATCH_NOTIFICATION_TYPES:
        return settings.get("match_notifications", True) is True

    if notification_type in PRODUCT_NOTIFICATION_TYPES:
        return settings.get("product_update_notifications", False) is True

    if notification_type in SECURITY_NOTIFICATION_TYPES:
        return settings.get("login_alerts", True) is True

    return True
