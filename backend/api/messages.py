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

    def translated_payload(message, current_user, selected_language=""):
        payload = deps["api_message_payload"](message, current_user.email)
        if selected_language:
            translated_text = deps["message_translation_service"].cached_translation(
                message, selected_language, deps["normalize_content_language_code"],
            )
            if translated_text:
                payload["translated_text"] = translated_text
                payload["translation_language"] = selected_language
        return payload

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
            if len(text) > 2000:
                return api_error("Message text is too long", 400)
            if len(reply_to) > 80:
                return api_error("Reply reference is too long", 400)

            messages = deps["load_messages"]()
            new_message = deps["message_service"].create_text_message(
                current_user.email,
                other_user.email,
                text,
                reply_to=reply_to,
                time_text=datetime.now().strftime("%d.%m.%Y %H:%M"),
                source_language=deps["detect_content_language"](text),
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

        messages = deps["load_messages"]()
        visible_messages = deps["message_service"].visible_chat_messages(
            messages,
            current_user.email,
            other_user.email,
        )

        settings = deps["normalize_user_ai_settings"](current_user.email)
        auto_translate = settings.get("auto_translate_messages") is True
        selected_language = str(settings.get("message_translation_language", "auto"))
        if selected_language == "auto":
            selected_language = deps["get_current_language"](current_user)
        selected_language = deps["normalize_content_language_code"](selected_language)

        translations_changed = False
        if auto_translate and deps["translation_provider_available"]():
            batch = deps["message_translation_service"].auto_translate_incoming(
                visible_messages,
                current_user.email,
                selected_language,
                deps["normalize_content_language_code"],
                deps["translate_message_text"],
                limit=20,
            )
            translations_changed = batch["changed"] > 0
            if translations_changed:
                deps["save_messages"](messages)

        return jsonify({
            "ok": True,
            "user": deps["api_user_payload"](other_user),
            "messages": [
                translated_payload(
                    message,
                    current_user,
                    selected_language if auto_translate and str(message.get("to", "")).lower() == current_user.email.lower() else "",
                )
                for message in visible_messages
            ],
            "auto_translation": {
                "enabled": auto_translate,
                "target_language": selected_language,
                "provider_available": bool(deps["translation_provider_available"]()),
            },
        })

    @messages_api.route("/api/chats/<path:other_email>/messages/<int:message_id>/translation", methods=["POST"])
    def api_message_translation(other_email, message_id):
        current_user, error = current_user_or_error()
        if error:
            return error
        other_user, error = target_user_or_error(other_email)
        if error:
            return error

        messages = deps["load_messages"]()
        visible = deps["message_service"].visible_chat_messages(
            messages, current_user.email, other_user.email,
        )
        message = None
        for item in visible:
            try:
                item_id = int(item.get("id", 0) or 0)
            except (TypeError, ValueError):
                continue
            if item_id == message_id:
                message = item
                break
        if message is None:
            return api_error("Message not found", 404)

        data = request.get_json(silent=True) or {}
        target_language = data.get("target_language") or deps["get_current_language"](current_user)
        result = deps["message_translation_service"].translate_message(
            message,
            target_language,
            deps["normalize_content_language_code"],
            deps["translate_message_text"],
        )
        if not result.get("ok"):
            status = 400 if result.get("error") == "unsupported_target_language" else 503
            return api_error(result.get("error", "translation_unavailable"), status)
        if not result.get("cached"):
            deps["save_messages"](messages)
        return jsonify({"ok": True, "translation": result})

    return messages_api
