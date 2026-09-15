from flask import Blueprint, abort, render_template


NOTIFICATION_ICONS = {
    "friend_request": "👥",
    "new_follower": "➕",
    "friend_request_accepted": "✅",
    "friend_request_declined": "🚫",
    "comment": "💬",
}
FRIEND_REQUEST_STATUSES = {"pending", "accepted", "declined"}


def create_notification_routes(deps):
    notification_routes = Blueprint("notification_routes", __name__)

    def page_copy(user):
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copy = {
            "ru": {
                "title": "Уведомления",
                "profile": "Профиль",
                "open_profile": "Открыть профиль",
                "accept": "Принять",
                "decline": "Отклонить",
                "accepted": "Принято",
                "declined": "Отклонено",
                "all_requests": "Все заявки",
                "empty_title": "Уведомлений пока нет",
                "empty_text": "Когда кто-то подпишется, отправит заявку, примет дружбу или прокомментирует — всё появится здесь.",
            },
            "de": {
                "title": "Benachrichtigungen",
                "profile": "Profil",
                "open_profile": "Profil öffnen",
                "accept": "Annehmen",
                "decline": "Ablehnen",
                "accepted": "Angenommen",
                "declined": "Abgelehnt",
                "all_requests": "Alle Anfragen",
                "empty_title": "Noch keine Benachrichtigungen",
                "empty_text": "Neue Follower, Freundschaftsanfragen und Kommentare erscheinen hier.",
            },
            "en": {
                "title": "Notifications",
                "profile": "Profile",
                "open_profile": "Open profile",
                "accept": "Accept",
                "decline": "Decline",
                "accepted": "Accepted",
                "declined": "Declined",
                "all_requests": "All requests",
                "empty_title": "No notifications yet",
                "empty_text": "New followers, friend requests and comments will appear here.",
            },
            "tr": {
                "title": "Bildirimler",
                "profile": "Profil",
                "open_profile": "Profili aç",
                "accept": "Kabul et",
                "decline": "Reddet",
                "accepted": "Kabul edildi",
                "declined": "Reddedildi",
                "all_requests": "Tüm istekler",
                "empty_title": "Henüz bildirim yok",
                "empty_text": "Yeni takipçiler, arkadaşlık istekleri ve yorumlar burada görünecek.",
            },
        }
        return ui, copy.get(language, copy["en"])

    @notification_routes.route("/notifications/<email>")
    @deps["login_required"]
    def notifications_page(email):
        user = deps["find_user_by_identifier"](email)
        if user is None:
            return "User not found", 404
        session_email = deps["normalize_email"](deps["current_session_email"]())
        if session_email != deps["normalize_email"](user.email):
            deps["log_security_event"]("notifications_owner_mismatch", session_email, f"target={user.email}")
            abort(403)

        cards = []
        for item in deps["get_notifications"](user.email):
            if isinstance(item, dict):
                text = deps["safe_text"](item.get("text", ""))
                created_at = deps["safe_text"](item.get("time_label") or item.get("created_at") or "")
                from_email = deps["normalize_email"](item.get("from_email") or item.get("from") or "")
                notification_type = str(item.get("type", "social"))
                request_status = str(item.get("status", "pending"))
            else:
                text = deps["safe_text"](item)
                created_at = ""
                from_email = ""
                notification_type = "social"
                request_status = "pending"

            if not text and not from_email:
                continue

            sender = deps["find_user_by_email"](from_email) if from_email else None
            if request_status not in FRIEND_REQUEST_STATUSES:
                request_status = "pending"

            cards.append({
                "text": text,
                "created_at": created_at,
                "icon": NOTIFICATION_ICONS.get(notification_type, "🔔"),
                "type": notification_type,
                "status": request_status,
                "read": bool(item.get("read", False)) if isinstance(item, dict) else False,
                "sender": {
                    "id": sender.id,
                    "email": sender.email,
                    "name": deps["safe_text"](sender.name),
                    "avatar_url": deps["get_avatar_url"](sender.email),
                } if sender is not None else None,
            })

        deps["mark_notifications_read"](user.email)
        ui, copy = page_copy(user)
        return render_template(
            "notifications.html",
            ui=ui,
            copy=copy,
            email=user.email,
            user_id=user.id,
            shell_account_target=user.id,
            notifications=cards,
            has_pending_requests=any(
                card["type"] == "friend_request" and card["status"] == "pending"
                for card in cards
            ),
            csrf_token_input=deps["csrf_input"](),
        )

    return notification_routes
