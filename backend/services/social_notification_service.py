EVENT_TEMPLATES = {
    "ru": {
        "follow": "{name} подписался на вас.",
        "friend_request": "{name} отправил вам заявку в друзья.",
        "friend_request_accepted": "{name} принял вашу заявку в друзья.",
        "friend_request_declined": "{name} отклонил вашу заявку в друзья.",
    },
    "en": {
        "follow": "{name} followed you.",
        "friend_request": "{name} sent you a friend request.",
        "friend_request_accepted": "{name} accepted your friend request.",
        "friend_request_declined": "{name} declined your friend request.",
    },
    "de": {
        "follow": "{name} folgt Ihnen jetzt.",
        "friend_request": "{name} hat Ihnen eine Freundschaftsanfrage gesendet.",
        "friend_request_accepted": "{name} hat Ihre Freundschaftsanfrage angenommen.",
        "friend_request_declined": "{name} hat Ihre Freundschaftsanfrage abgelehnt.",
    },
    "tr": {
        "follow": "{name} sizi takip etmeye başladı.",
        "friend_request": "{name} size arkadaşlık isteği gönderdi.",
        "friend_request_accepted": "{name} arkadaşlık isteğinizi kabul etti.",
        "friend_request_declined": "{name} arkadaşlık isteğinizi reddetti.",
    },
}


def social_notification_text(event_type, actor_name, language):
    language_code = str(language or "en").strip().lower().split("-", 1)[0]
    templates = EVENT_TEMPLATES.get(language_code, EVENT_TEMPLATES["en"])
    template = templates.get(str(event_type or ""), "{name}")
    return template.format(name=str(actor_name or "").strip())
