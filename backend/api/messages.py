from datetime import datetime

from flask import Blueprint, jsonify, request


def create_messages_api(deps):
    messages_api = Blueprint("messages_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    def current_user_or_error():
        user = deps["get_api_current_user"]()
        if user is None:
            return None, api_error("Authentication required", 401)
        return user, None

    def target_user_or_error(target_email):
        target_user = deps["find_user_by_email"](target_email)
        if target_user is None:
            return None, api_error("User not found", 404)
        return target_user, None

    @messages_api.route("/api/chats")
    def api_chats():
        current_user, error = current_user_or_error()
        if error:
            return error

        conversations = []
        for item in deps["message_service"].chat_summaries(
            deps["load_messages"](),
            current_user.email,
            deps["find_user_by_email"],
            deps["is_blocked"],
        ):
            conversations.append({
                "user": deps["api_user_payload"](item["user"]),
                "last_message": deps["api_message_payload"](item["last_message"], current_user.email),
            })

        return jsonify({
            "ok": True,
            "chats": conversations,
        })

    @messages_api.route("/api/chats/<path:other_email>/messages", methods=["GET", "POST"])
    def api_chat_messages(other_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        other_user, error = target_user_or_error(other_email)
        if error:
            return error

        can_write, block_title, block_text = deps["get_message_permission_status"](current_user, other_user)
        if not can_write:
            return api_error(block_text or block_title, 403)

        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            text = deps["clean_text"](data.get("message", "")).strip()
            reply_to = deps["clean_text"](data.get("reply_to", "")).strip()

            if not text:
                return api_error("Message text is required", 400)

            messages = deps["load_messages"]()
            new_message = deps["message_service"].create_text_message(
                current_user.email,
                other_user.email,
                text,
                reply_to=reply_to,
                time_text=datetime.now().strftime("%d.%m.%Y %H:%M"),
            )
            deps["message_service"].append_message(messages, new_message)
            deps["save_messages"](messages)

            deps["create_social_notification"](
                other_user.email,
                f"{current_user.name}: {text[:90]}",
                "message",
                current_user.email,
            )

            return jsonify({
                "ok": True,
                "message": deps["api_message_payload"](new_message, current_user.email),
            }), 201

        visible_messages = deps["message_service"].visible_chat_messages(
            deps["load_messages"](),
            current_user.email,
            other_user.email,
        )

        return jsonify({
            "ok": True,
            "user": deps["api_user_payload"](other_user),
            "messages": [
                deps["api_message_payload"](message, current_user.email)
                for message in visible_messages
            ],
        })

    return messages_api
