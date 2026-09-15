def can_message_user(message_permission, viewer_verified, are_friends_value):
    if message_permission == "everyone":
        return True
    if message_permission == "friends" and are_friends_value:
        return True
    if message_permission == "verified" and viewer_verified:
        return True
    return False


DEFAULT_UI = {
    "dashboard": "Главная",
    "settings": "Настройки",
    "following": "Подписки",
    "follow": "Подписаться",
    "message": "Сообщение",
    "messages_closed": "Сообщение закрыто",
    "unblock": "Разблокировать",
    "block": "Заблокировать",
    "unrestrict": "Снять ограничение",
    "restrict": "Ограничить",
    "show_stories": "Показывать истории",
    "hide_my_stories": "Скрыть мои истории",
    "more": "Ещё",
    "copy_link": "Скопировать ссылку",
    "link_copied": "Ссылка скопирована",
    "share_profile": "Поделиться профилем",
    "qr_code": "QR-код",
    "report": "Пожаловаться",
    "cancel": "Отмена",
}


def build_profile_actions(context, ui=None):
    ui = ui or DEFAULT_UI

    def text(key):
        return str(ui.get(key, DEFAULT_UI.get(key, key)))

    viewer_email = context["viewer_email"]
    owner_email = context["owner_email"]
    viewer_id = context.get("viewer_id") or viewer_email
    owner_id = context.get("owner_id") or owner_email

    def form(path, label, css_class=""):
        return {"kind": "form", "url": path, "label": label, "class": css_class}

    def link(path, label, css_class=""):
        return {"kind": "link", "url": path, "label": label, "class": css_class}

    if context.get("is_own_profile"):
        return {
            "primary": [
                link(f"/dashboard/{owner_email}", text("dashboard"), "primary"),
                link(f"/settings/{owner_email}", text("settings")),
            ],
            "menu": [],
        }

    if context.get("viewer_follows_user"):
        follow_button = form(f"/unfollow/{viewer_id}/{owner_id}", text("following"))
    else:
        follow_button = form(f"/follow/{viewer_id}/{owner_id}", text("follow"), "primary")

    message_permission = context.get("message_permission", "everyone")
    message_allowed = can_message_user(
        message_permission,
        context.get("viewer_verified") is True,
        context.get("are_friends") is True,
    )
    if message_allowed:
        message_button = link(f"/chat/{viewer_email}/{owner_email}", text("message"))
    else:
        message_button = {"kind": "disabled", "label": text("messages_closed"), "class": "disabled"}

    if context.get("viewer_blocked_user"):
        block_menu_item = form(f"/unblock_user/{viewer_email}/{owner_email}", text("unblock"))
    else:
        block_menu_item = form(f"/block_user/{viewer_email}/{owner_email}", text("block"), "danger-link")

    if context.get("is_restricted"):
        restrict_menu_item = form(f"/unrestrict_user/{viewer_email}/{owner_email}", text("unrestrict"))
    else:
        restrict_menu_item = form(f"/restrict_user/{viewer_email}/{owner_email}", text("restrict"))

    if context.get("has_hidden_stories"):
        stories_menu_item = form(f"/show_stories/{viewer_email}/{owner_email}", text("show_stories"))
    else:
        stories_menu_item = form(f"/hide_stories/{viewer_email}/{owner_email}", text("hide_my_stories"))

    return {
        "primary": [follow_button, message_button],
        "more_label": text("more"),
        "copied_label": text("link_copied"),
        "menu": [
            {"kind": "copy", "label": text("copy_link")},
            {"kind": "share", "label": text("share_profile")},
            link(f"/profile_qr/{viewer_email}/{owner_email}", text("qr_code")),
            stories_menu_item,
            restrict_menu_item,
            link(f"/report_user/{viewer_email}/{owner_email}", text("report")),
            block_menu_item,
            {"kind": "cancel", "label": text("cancel"), "class": "cancel-link"},
        ],
    }
