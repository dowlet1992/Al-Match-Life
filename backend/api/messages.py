import base64
import re
import secrets
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

    def private_json(payload, status_code=200):
        response = jsonify(payload)
        response.status_code = status_code
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def requested_message_page():
        try:
            limit = int(request.args.get("limit", "50"))
        except (TypeError, ValueError):
            return None, None, api_error("Invalid limit", 400)
        if limit < 1 or limit > 100:
            return None, None, api_error("Limit must be between 1 and 100", 400)

        cursor = deps["clean_text"](request.args.get("cursor", ""))
        if not cursor:
            return limit, None, None
        if len(cursor) > 64:
            return None, None, api_error("Invalid cursor", 400)
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode("ascii")
            before_id = int(decoded)
        except (UnicodeError, ValueError):
            return None, None, api_error("Invalid cursor", 400)
        if before_id < 1 or str(before_id) != decoded:
            return None, None, api_error("Invalid cursor", 400)
        return limit, before_id, None

    def encode_message_cursor(message_id):
        return base64.urlsafe_b64encode(str(message_id).encode("ascii")).decode("ascii").rstrip("=")

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

    def message_response_payload(message, current_user):
        payload = deps["api_message_payload"](message, current_user.email)
        payload.pop("translations", None)
        return payload

    def translated_payload(message, current_user, selected_language=""):
        payload = message_response_payload(message, current_user)
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
                "user": deps["api_compact_user_payload"](item["user"]),
                "last_message": message_response_payload(item["last_message"], current_user),
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
            supplied_client_message_id = str(data.get("client_message_id", "")).strip()
            client_message_id = supplied_client_message_id or secrets.token_urlsafe(18)

            if not text:
                return api_error("Message text is required", 400)
            if len(text) > 2000:
                return api_error("Message text is too long", 400)
            if len(reply_to) > 80:
                return api_error("Reply reference is too long", 400)
            if supplied_client_message_id and not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", client_message_id):
                return api_error("Invalid client message ID", 400)

            messages = deps["load_messages"]()
            existing = deps["message_service"].find_client_message(
                messages, current_user.email, other_user.email, client_message_id,
            )
            if existing is not None:
                return private_json({
                    "ok": True, "duplicate": True,
                    "message": message_response_payload(existing, current_user),
                })
            new_message = deps["message_service"].create_text_message(
                current_user.email,
                other_user.email,
                text,
                reply_to=reply_to,
                time_text=datetime.now().strftime("%d.%m.%Y %H:%M"),
                source_language=deps["detect_content_language"](text),
                client_message_id=client_message_id,
            )
            deps["message_service"].append_message(messages, new_message)
            deps["save_messages"](messages)

            deps["create_social_notification"](
                other_user.email,
                f"{current_user.name}: {text[:90]}",
                "message",
                current_user.email,
            )

            return private_json({
                "ok": True,
                "message": message_response_payload(new_message, current_user),
            }, 201)

        messages = deps["load_messages"]()
        visible_messages = deps["message_service"].visible_chat_messages(
            messages,
            current_user.email,
            other_user.email,
        )
        read_changed = False
        for message in visible_messages:
            if (str(message.get("from", "")).lower() == other_user.email.lower()
                    and str(message.get("to", "")).lower() == current_user.email.lower()
                    and message.get("status") != "read"):
                message["status"] = "read"
                read_changed = True
        limit, before_id, error = requested_message_page()
        if error:
            return error
        if before_id is not None:
            visible_messages = [
                message for message in visible_messages
                if int(message.get("id", 0) or 0) < before_id
            ]
        try:
            after_id = max(int(request.args.get("after_id", "0") or 0), 0)
        except (TypeError, ValueError):
            return api_error("Invalid after_id", 400)
        if after_id:
            visible_messages = [message for message in visible_messages if int(message.get("id", 0) or 0) > after_id]
        has_more = len(visible_messages) > limit
        page_messages = visible_messages[-limit:]
        next_cursor = (
            encode_message_cursor(page_messages[0].get("id"))
            if has_more and page_messages else None
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
                page_messages,
                current_user.email,
                selected_language,
                deps["normalize_content_language_code"],
                deps["translate_message_text"],
                limit=20,
            )
            translations_changed = batch["changed"] > 0
        if translations_changed or read_changed:
            deps["save_messages"](messages)

        peer_read_through_id = max([
            int(message.get("id", 0) or 0) for message in messages
            if isinstance(message, dict) and str(message.get("from", "")).lower() == current_user.email.lower()
            and str(message.get("to", "")).lower() == other_user.email.lower() and message.get("status") == "read"
        ] or [0])

        return private_json({
            "ok": True,
            "user": deps["api_compact_user_payload"](other_user),
            "messages": [
                translated_payload(
                    message,
                    current_user,
                    selected_language if auto_translate and str(message.get("to", "")).lower() == current_user.email.lower() else "",
                )
                for message in page_messages
            ],
            "next_cursor": next_cursor,
            "peer_read_through_id": peer_read_through_id,
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
