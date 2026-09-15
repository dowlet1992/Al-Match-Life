from backend.services.social_notification_service import social_notification_text


def test_social_notifications_use_recipient_language():
    assert social_notification_text("follow", "Alice", "ru") == "Alice подписался на вас."
    assert social_notification_text("follow", "Alice", "en") == "Alice followed you."
    assert social_notification_text("follow", "Alice", "de") == "Alice folgt Ihnen jetzt."


def test_social_notifications_cover_friend_request_lifecycle():
    assert social_notification_text("friend_request", "Bob", "en") == "Bob sent you a friend request."
    assert social_notification_text("friend_request_accepted", "Bob", "de") == (
        "Bob hat Ihre Freundschaftsanfrage angenommen."
    )
    assert social_notification_text("friend_request_declined", "Bob", "ru") == (
        "Bob отклонил вашу заявку в друзья."
    )


def test_social_notification_language_falls_back_to_english():
    assert social_notification_text("follow", "Alice", "fr-FR") == "Alice followed you."
