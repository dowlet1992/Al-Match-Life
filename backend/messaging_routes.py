from flask import Blueprint, abort, render_template


def create_messaging_routes(deps):
    routes = Blueprint("messaging_routes", __name__)

    @routes.route("/messages/<identifier>")
    @deps["login_required"]
    def messages_page(identifier):
        current_user = deps["find_user_by_identifier"](identifier)
        if current_user is None:
            return "User not found", 404
        session_email = deps["normalize_email"](deps["current_session_email"]())
        if session_email != deps["normalize_email"](current_user.email):
            deps["log_security_event"]("messages_access_denied", session_email, f"target={current_user.email}")
            abort(403)
        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        dialogs, unread = {}, {}
        for message in deps["load_messages"]():
            sender, receiver = message.get("from"), message.get("to")
            if sender == current_user.email:
                other_email = receiver
            elif receiver == current_user.email:
                other_email = sender
                if message.get("status") != "read":
                    unread[other_email] = unread.get(other_email, 0) + 1
            else:
                continue
            other = deps["find_user_by_email"](other_email)
            if other is None or deps["blocked_or_restricted"](current_user.email, other.email):
                continue
            dialogs[other_email] = message
        dialog_views = []
        for other_email, last_message in dialogs.items():
            other = deps["find_user_by_email"](other_email)
            if other is None:
                continue
            dialog_views.append({
                "name": other.name, "profession": other.profession, "message": last_message.get("message", ""),
                "avatar_url": deps["get_avatar_url"](other.email), "unread_count": unread.get(other.email, 0),
                "chat_url": f"/chat/{current_user.id}/{other.id}",
            })
        contacts = []
        for other in deps["get_users"]():
            if deps["normalize_email"](other.email) == deps["normalize_email"](current_user.email):
                continue
            if deps["blocked_or_restricted"](current_user.email, other.email):
                continue
            allowed, title, text = deps["message_permission_status"](current_user, other)
            contacts.append({
                "name": other.name, "profession": other.profession, "avatar_url": deps["get_avatar_url"](other.email),
                "can_write": allowed, "permission_title": title, "permission_text": text,
                "chat_url": f"/chat/{current_user.id}/{other.id}",
            })
        return render_template(
            "messages.html", ui=ui, email=current_user.email, user_id=current_user.id,
            shell_account_target=current_user.id, dialogs=dialog_views, contacts=contacts,
        )

    return routes
