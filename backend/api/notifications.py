from flask import Blueprint, jsonify


def create_notifications_api(deps):
    notifications_api = Blueprint("notifications_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    @notifications_api.route("/api/notifications")
    def api_notifications():
        user = deps["get_api_current_user"]()
        if user is None:
            return api_error("Authentication required", 401)

        notifications = []
        for item in deps["get_notifications"](user.email):
            if not isinstance(item, dict):
                continue

            notifications.append({
                "type": deps["clean_text"](item.get("type", "system")),
                "text": deps["clean_text"](item.get("text", "")),
                "from_email": deps["normalize_email"](item.get("from_email") or item.get("from") or ""),
                "read": bool(item.get("read", False)),
                "created_at": deps["clean_text"](item.get("created_at_iso") or item.get("created_at") or ""),
                "time_label": deps["clean_text"](item.get("time_label", "")),
            })

        return jsonify({
            "ok": True,
            "notifications": notifications,
        })

    return notifications_api
