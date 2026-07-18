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


def render_profile_actions(context, safe_text, ui=None):
    ui = ui or DEFAULT_UI

    def text(key):
        return safe_text(ui.get(key, DEFAULT_UI.get(key, key)))

    viewer_email = context["viewer_email"]
    owner_email = context["owner_email"]

    if context.get("is_own_profile"):
        return f"""
        <a class="profile-action primary" href="/dashboard/{safe_text(owner_email)}">{text("dashboard")}</a>
        <a class="profile-action" href="/settings/{safe_text(owner_email)}">{text("settings")}</a>
        """

    if context.get("viewer_follows_user"):
        follow_button = f'<a class="profile-action" href="/unfollow/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("following")}</a>'
    else:
        follow_button = f'<a class="profile-action primary" href="/follow/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("follow")}</a>'

    message_permission = context.get("message_permission", "everyone")
    message_allowed = can_message_user(
        message_permission,
        context.get("viewer_verified") is True,
        context.get("are_friends") is True,
    )
    if message_allowed:
        message_button = f'<a class="profile-action" href="/chat/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("message")}</a>'
    else:
        message_button = f'<span class="profile-action disabled">{text("messages_closed")}</span>'

    if context.get("viewer_blocked_user"):
        block_menu_item = f'<a href="/unblock_user/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("unblock")}</a>'
    else:
        block_menu_item = f'<a class="danger-link" href="/block_user/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("block")}</a>'

    if context.get("is_restricted"):
        restrict_menu_item = f'<a href="/unrestrict_user/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("unrestrict")}</a>'
    else:
        restrict_menu_item = f'<a href="/restrict_user/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("restrict")}</a>'

    if context.get("has_hidden_stories"):
        stories_menu_item = f'<a href="/show_stories/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("show_stories")}</a>'
    else:
        stories_menu_item = f'<a href="/hide_stories/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("hide_my_stories")}</a>'

    more_menu = f"""
        <details class="profile-more-menu">
            <summary aria-label="{text("more")}">⋯</summary>
            <div class="profile-more-list">
                <a href="#" onclick="navigator.clipboard && navigator.clipboard.writeText(window.location.href); this.textContent='{text("link_copied")}'; return false;">{text("copy_link")}</a>
                <a href="#" onclick="if (navigator.share) {{ navigator.share({{title: document.title, url: window.location.href}}); }} else if (navigator.clipboard) {{ navigator.clipboard.writeText(window.location.href); this.textContent='{text("link_copied")}'; }} return false;">{text("share_profile")}</a>
                <a href="/profile_qr/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("qr_code")}</a>
                {stories_menu_item}
                {restrict_menu_item}
                <a href="/report_user/{safe_text(viewer_email)}/{safe_text(owner_email)}">{text("report")}</a>
                {block_menu_item}
                <a class="cancel-link" href="#" onclick="this.closest('details').removeAttribute('open'); return false;">{text("cancel")}</a>
            </div>
        </details>
        """

    return follow_button + message_button + more_menu
