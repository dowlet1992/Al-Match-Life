import json
import os
import secrets
import time
from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session
from werkzeug.utils import secure_filename
from backend.i18n import LANGUAGE_CATALOG


chat_call_routes = Blueprint("chat_call_routes", __name__)
_DEPS = {}


def configure_chat_call_routes(deps):
    _DEPS.clear()
    _DEPS.update(deps)
    globals().update(deps)


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        return _DEPS["login_required"](function)(*args, **kwargs)
    return wrapper


@chat_call_routes.route("/pending_call/<current_email>/<other_email>")
@login_required
def pending_call(current_email, other_email):
    current_user = find_user_by_email(current_email)
    other_user = find_user_by_email(other_email)

    if current_user is None or other_user is None:
        return {"ok": False, "pending": False}

    if is_blocked(current_user.email, other_user.email) or is_blocked(other_user.email, current_user.email):
        return {"ok": True, "pending": False}

    if is_restricted(current_user.email, other_user.email) or is_restricted(other_user.email, current_user.email):
        return {"ok": True, "pending": False}

    pending = find_pending_call_for_chat(current_user.email, other_user.email)
    if not pending:
        return {"ok": True, "pending": False}

    call_type = pending.get("call_type", "audio")
    accept_url = f"/{call_type}_call/{safe_text(current_user.email)}/{safe_text(other_user.email)}?mode=receiver"
    decline_url = f"/decline_call/{safe_text(current_user.email)}/{safe_text(other_user.email)}/{safe_text(call_type)}"

    return {
        "ok": True,
        "pending": True,
        "call_id": pending.get("call_id", ""),
        "call_type": call_type,
        "caller_name": safe_text(other_user.name),
        "caller_avatar": get_avatar_url(other_user.email),
        "accept_url": accept_url,
        "decline_url": decline_url
    }


@chat_call_routes.route("/decline_call/<current_email>/<other_email>/<call_type>", methods=["POST"])
@login_required
def decline_call(current_email, other_email, call_type):
    validate_csrf_token()
    current_user = find_user_by_email(current_email)
    other_user = find_user_by_email(other_email)

    if current_user is None or other_user is None:
        return {"ok": False, "error": "user_not_found"}, 404

    call_type = clean_text(call_type)
    if call_type not in {"audio", "video"}:
        call_type = "audio"

    call_id = get_call_room_id(current_user.email, other_user.email, call_type)
    declined_signal = {
        "id": secrets.token_urlsafe(10),
        "type": "declined",
        "from": normalize_email(current_user.email),
        "to": normalize_email(other_user.email),
        "payload": {"declined_at": datetime.now().isoformat()},
        "created_at": datetime.now().timestamp()
    }
    closed_room = append_call_signal(
        call_id,
        declined_signal,
        status="declined",
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        close=True,
        enforce_transition=True,
    )
    if closed_room == "invalid_transition":
        return {"ok": False, "error": "invalid_call_transition"}, 409
    if closed_room is not None:
        record_call_chat_event(other_user.email, current_user.email, call_type, "declined")

    return {"ok": True}


@chat_call_routes.route("/call_signal/<call_id>/ack", methods=["POST"])
@login_required
def acknowledge_call_signal_delivery(call_id):
    validate_csrf_token()
    if request.content_length is not None and request.content_length > call_signal_security_service.MAX_SIGNAL_REQUEST_BYTES:
        return {"ok": False, "error": "signal_request_too_large"}, 413
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_ack_request"}, 400
    logged_email = normalize_email(session.get("user_email", ""))
    other_email = normalize_email(data.get("other_email", ""))
    call_type = clean_text(data.get("call_type", ""))
    event_ids = call_signal_security_service.normalize_ack_event_ids(data.get("event_ids"))
    if call_type not in {"audio", "video"} or not other_email or not event_ids:
        return {"ok": False, "error": "invalid_ack_request"}, 400
    expected_call_id = get_call_room_id(logged_email, other_email, call_type)
    call_id = secure_filename(call_id)
    if not secrets.compare_digest(call_id, expected_call_id):
        return {"ok": False, "error": "forbidden_room"}, 403
    if is_blocked(logged_email, other_email) or is_blocked(other_email, logged_email):
        return {"ok": False, "error": "blocked"}, 403
    if is_restricted(logged_email, other_email) or is_restricted(other_email, logged_email):
        return {"ok": False, "error": "restricted"}, 403
    if not get_call_signal_poll_limiter().allow(f"ack::{logged_email}::{call_id}"):
        response = jsonify({"ok": False, "error": "signal_ack_rate_limited"})
        response.status_code = 429
        response.headers["Retry-After"] = "1"
        return response
    status, acknowledged = acknowledge_call_signals(
        call_id, logged_email, event_ids, datetime.now().timestamp(),
    )
    if status == "missing":
        return {"ok": False, "error": "call_room_not_found"}, 404
    return {"ok": True, "acknowledged_event_ids": event_ids, "acknowledged_count": acknowledged}


@chat_call_routes.route("/call_signal/<call_id>", methods=["GET", "POST"])
@login_required
def call_signal(call_id):
    call_id = secure_filename(call_id)
    logged_email = normalize_email(session.get("user_email", ""))

    if request.method == "POST":
        validate_csrf_token()
        if request.content_length is not None and request.content_length > call_signal_security_service.MAX_SIGNAL_REQUEST_BYTES:
            log_security_event("call_signal_payload_rejected", logged_email, "reason=request_too_large")
            return {"ok": False, "error": "signal_request_too_large"}, 413
        request_payload = request.get_json(silent=True) or {}
        if not isinstance(request_payload, dict):
            return {"ok": False, "error": "invalid_signal_request"}, 400
        sender_email = normalize_email(request_payload.get("from", ""))
        receiver_email = normalize_email(request_payload.get("to", ""))
        signal_payload = request_payload.get("payload", {})
        call_type = clean_text(
            signal_payload.get("call_type", "") if isinstance(signal_payload, dict) else ""
        )
    else:
        request_payload = {}
        sender_email = logged_email
        receiver_email = normalize_email(request.args.get("other", ""))
        call_type = clean_text(request.args.get("call_type", ""))

    if call_type not in {"audio", "video"}:
        return {"ok": False, "error": "invalid_call_type"}, 400

    if not sender_email or not receiver_email:
        return {"ok": False, "error": "missing_participants"}, 400

    if logged_email != sender_email:
        log_security_event("call_signal_identity_rejected", logged_email, f"Attempted sender={sender_email}")
        return {"ok": False, "error": "forbidden_participant"}, 403

    expected_call_id = get_call_room_id(sender_email, receiver_email, call_type)
    if not secrets.compare_digest(call_id, expected_call_id):
        log_security_event("call_signal_room_rejected", logged_email, f"Rejected room={call_id}")
        return {"ok": False, "error": "forbidden_room"}, 403

    if is_blocked(sender_email, receiver_email) or is_blocked(receiver_email, sender_email):
        return {"ok": False, "error": "blocked"}, 403

    if is_restricted(sender_email, receiver_email) or is_restricted(receiver_email, sender_email):
        log_security_event("call_signal_restricted", sender_email, f"Restricted call signal with {receiver_email}")
        return {"ok": False, "error": "restricted"}, 403

    if request.method == "GET" and not get_call_signal_poll_limiter().allow(f"{logged_email}::{call_id}"):
        response = jsonify({"ok": False, "error": "signal_poll_rate_limited"})
        response.status_code = 429
        response.headers["Retry-After"] = "1"
        return response

    timeout_result = None
    if request.method == "GET":
        timeout_result = expire_call_signal_room(call_id, datetime.now().timestamp())
    room = (
        timeout_result.get("room") if isinstance(timeout_result, dict)
        else get_call_signal_room(call_id)
    ) or {"messages": [], "status": "active", "updated_at": ""}

    if isinstance(timeout_result, dict) and isinstance(timeout_result.get("transition"), dict):
        transition = timeout_result["transition"]
        transition_payload = transition.get("payload", {}) if isinstance(transition.get("payload"), dict) else {}
        record_call_chat_event(
            transition.get("from", sender_email), transition.get("to", receiver_email),
            transition_payload.get("call_type", call_type), transition.get("type", "ended"),
        )

    if not isinstance(room, dict):
        room = {"messages": [], "status": "active", "updated_at": ""}

    if not isinstance(room.get("messages"), list):
        room["messages"] = []

    if request.method == "POST":
        signal_type = clean_text(request_payload.get("type", ""))
        event_id = call_signal_security_service.normalize_event_id(request_payload.get("event_id", ""))

        allowed_types = {"offer", "answer", "ice", "ringing", "accepted", "declined", "ended", "conference_upgrade"}
        if signal_type not in allowed_types:
            return {"ok": False, "error": "invalid_signal_type"}, 400
        if not event_id:
            return {"ok": False, "error": "invalid_signal_event_id"}, 400

        if not sender_email or not receiver_email:
            return {"ok": False, "error": "missing_participants"}, 400

        signal_payload, payload_error = call_signal_security_service.validate_signal_payload(signal_type, signal_payload)
        if payload_error:
            log_security_event("call_signal_payload_rejected", sender_email, f"type={signal_type}; reason={payload_error}")
            return {"ok": False, "error": payload_error}, 400

        now_timestamp = datetime.now().timestamp()
        signal_message = {
            "id": event_id,
            "type": signal_type,
            "from": sender_email,
            "to": receiver_email,
            "payload": signal_payload,
            "created_at": now_timestamp
        }
        push_event = None
        if signal_type == "ringing":
            push_event = {
                "event_id": event_id,
                "target_email": receiver_email,
                "event_type": "incoming_call",
                "payload": {
                    "call_id": call_id,
                    "call_type": call_type,
                    "caller_email": sender_email,
                    "receiver_email": receiver_email,
                },
                "created_at": now_timestamp,
                "expires_at": now_timestamp + 45,
                "attempts": 0,
                "status": "pending",
            }
        elif signal_type in {"declined", "ended"}:
            push_event = call_cancel_push_event(call_id, room, signal_message, now_timestamp)
        closed_signal_types = {"declined", "ended", "missed"}
        rate_limit, rate_window = call_signal_security_service.SIGNAL_RATE_LIMITS[signal_type]
        stored_room = append_call_signal(
            call_id,
            signal_message,
            status=signal_type if signal_type in closed_signal_types else "active",
            updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            close=signal_type in closed_signal_types,
            rate_limit=rate_limit,
            rate_window=rate_window,
            enforce_transition=True,
            push_event=push_event,
        )
        if stored_room == "rate_limited":
            log_security_event("call_signal_rate_limited", sender_email, f"type={signal_type}")
            response = jsonify({"ok": False, "error": "signal_rate_limited"})
            response.status_code = 429
            response.headers["Retry-After"] = "1"
            return response
        if stored_room == "invalid_transition":
            log_security_event("call_signal_transition_rejected", sender_email, f"type={signal_type}")
            return {"ok": False, "error": "invalid_call_transition"}, 409
        if stored_room == "idempotency_conflict":
            log_security_event("call_signal_idempotency_conflict", sender_email, f"type={signal_type}")
            return {"ok": False, "error": "signal_idempotency_conflict", "event_id": event_id}, 409
        duplicate_signal = isinstance(stored_room, dict) and stored_room.pop("_signal_duplicate", False) is True
        if stored_room is not None:
            room = stored_room

        if signal_type in closed_signal_types and stored_room is not None and not duplicate_signal:
            call_type = clean_text(signal_payload.get("call_type", "")) if isinstance(signal_payload, dict) else ""
            if call_type not in {"audio", "video"}:
                call_type = "video" if "video" in call_id else "audio"

            duration_seconds = 0
            if signal_type == "ended":
                try:
                    accepted_times = [float(room.get("accepted_at", 0) or 0)]
                except (TypeError, ValueError):
                    accepted_times = []
                for signal_message in room.get("messages", []):
                    if clean_text(signal_message.get("type", "")) == "accepted":
                        try:
                            accepted_times.append(float(signal_message.get("created_at", 0) or 0))
                        except Exception:
                            continue
                if accepted_times:
                    duration_seconds = max(0, now_timestamp - max(accepted_times))

            record_call_chat_event(sender_email, receiver_email, call_type, signal_type, duration_seconds)

        return {"ok": True, "event_id": event_id, "duplicate": duplicate_signal}

    after = clean_text(request.args.get("after", "0"))
    try:
        after_value = float(after)
    except Exception:
        after_value = 0

    messages = []
    acknowledgments = []
    for message in room.get("messages", []):
        message_from = normalize_email(message.get("from", ""))
        acknowledged_by = normalize_email(message.get("acknowledged_by", ""))
        if message_from == logged_email:
            if acknowledged_by and message.get("id"):
                acknowledgments.append(str(message.get("id")))
            continue
        if float(message.get("created_at", 0) or 0) <= after_value and (
            not message.get("id") or acknowledged_by == logged_email
        ):
            continue
        messages.append(message)

    return {
        "ok": True,
        "status": room.get("status", "active"),
        "messages": messages,
        "acknowledged_event_ids": acknowledgments[-100:],
        "server_time": datetime.now().timestamp()
    }


@chat_call_routes.route("/audio_call/<sender_email>/<receiver_email>")
@login_required
def audio_call_page(sender_email, receiver_email):
    sender = find_user_by_email(sender_email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return "User not found"

    if is_blocked(receiver.email, sender.email) or is_blocked(sender.email, receiver.email):
        log_security_event("call_blocked", sender.email, f"Blocked audio call attempt to {receiver.email}")
        return simple_page(
            "🚫 Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей заблокировал другого.",
            sender.email
        )

    if is_restricted(receiver.email, sender.email) or is_restricted(sender.email, receiver.email):
        log_security_event("call_restricted", sender.email, f"Restricted audio call attempt to {receiver.email}")
        return simple_page(
            "Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей ограничил связь.",
            sender.email
        )

    call_role = clean_text(request.args.get("mode", "caller"))
    if call_role not in {"caller", "receiver"}:
        call_role = "caller"

    return render_call_page(sender, receiver, "audio", call_role)


@chat_call_routes.route("/video_call/<sender_email>/<receiver_email>")
@login_required
def video_call_page(sender_email, receiver_email):
    sender = find_user_by_email(sender_email)
    receiver = find_user_by_email(receiver_email)

    if sender is None or receiver is None:
        return "User not found"

    if is_blocked(receiver.email, sender.email) or is_blocked(sender.email, receiver.email):
        log_security_event("call_blocked", sender.email, f"Blocked video call attempt to {receiver.email}")
        return simple_page(
            "🚫 Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей заблокировал другого.",
            sender.email
        )

    if is_restricted(receiver.email, sender.email) or is_restricted(sender.email, receiver.email):
        log_security_event("call_restricted", sender.email, f"Restricted video call attempt to {receiver.email}")
        return simple_page(
            "Звонок недоступен",
            "Звонок невозможен, потому что один из пользователей ограничил связь.",
            sender.email
        )

    call_role = clean_text(request.args.get("mode", "caller"))
    if call_role not in {"caller", "receiver"}:
        call_role = "caller"

    return render_call_page(sender, receiver, "video", call_role)


def render_call_page(sender, receiver, call_type, call_role="caller"):
    is_video = call_type == "video"
    ui = translation_bundle(get_current_language(sender))
    title = ui.get("video_call", "Video call") if is_video else ui.get("audio_call", "Audio call")
    icon = "🎥" if is_video else "📞"
    receiver_avatar = get_avatar_url(receiver.email)
    sender_avatar = get_avatar_url(sender.email)
    call_id = get_call_room_id(sender.email, receiver.email, call_type)
    need_video = "true" if is_video else "false"
    is_caller = "true" if call_role == "caller" else "false"
    call_settings = normalize_user_ai_settings(sender.email)
    captions_allowed = "true" if call_settings.get("live_call_captions") is True else "false"
    server_transcription_allowed = "true" if call_settings.get("allow_server_call_transcription") is True else "false"
    realtime_transcription_available = "true" if realtime_speech_service.provider_available() else "false"
    ai_voice_translation_allowed = "true" if call_settings.get("allow_ai_voice_translation") is True else "false"
    voice_translation_enabled = "true" if (
        call_settings.get("allow_ai_voice_translation") is True
        and call_settings.get("call_voice_translation_enabled") is True
    ) else "false"
    auto_translate_captions = "true" if call_settings.get("auto_translate_call_captions") is True else "false"
    caption_target_language = str(call_settings.get("call_caption_language", "auto"))
    if caption_target_language == "auto":
        caption_target_language = get_current_language(sender)
    caption_target_language = normalize_content_language_code(caption_target_language)
    configured_spoken_language = str(call_settings.get("call_spoken_language", "auto")).strip().lower()
    recognition_language = "" if configured_spoken_language == "auto" else normalize_content_language_code(configured_spoken_language)
    call_config = {
        "need_video": need_video,
        "is_caller": is_caller,
        "captions_allowed": captions_allowed,
        "server_transcription_allowed": server_transcription_allowed,
        "realtime_transcription_available": realtime_transcription_available,
        "ai_voice_translation_allowed": ai_voice_translation_allowed,
        "voice_translation_enabled": voice_translation_enabled,
        "auto_translate_captions": auto_translate_captions,
        "caption_target_language": caption_target_language,
        "recognition_language": recognition_language,
        "call_id": call_id,
        "current_user": sender.email,
        "other_user": receiver.email,
        "call_type": call_type,
        "csrf_token": get_csrf_token(),
        "receiver_name": receiver.name,
        "i18n": {
            key: ui.get(key, key)
            for key in (
                "call_in_progress", "call_reconnect_failed", "offline_waiting",
                "reconnecting_attempt", "you", "live_captions",
                "server_transcription_unavailable", "server_transcription_paused",
                "server_transcription_connection_error", "captions_disabled_help",
                "local_recognition_unavailable", "speech_recognition_unavailable",
                "connecting", "requesting_media_access", "connection_interrupted",
                "call_ended", "waiting_for_answer", "joining_incoming_call",
                "media_access_denied", "offline_call_recovery", "translation_label",
                "call_translation_ready",
                "call_translating", "call_speaking_translation",
                "call_translation_saved", "call_translation_local_only",
                "call_quality_excellent", "call_quality_good", "call_quality_fair",
                "call_quality_poor", "call_quality_offline",
                "conference_unavailable", "add_people", "no_available_people",
                "share_screen", "stop_sharing_screen", "screen_share_active",
                "screen_share_stopped", "screen_share_unavailable",
            )
        },
    }
    return render_template(
        "call.html",
        ui=ui,
        title=title,
        icon=icon,
        sender=sender,
        receiver=receiver,
        sender_avatar=sender_avatar,
        receiver_avatar=receiver_avatar,
        is_video=is_video,
        config=call_config,
        call_languages=LANGUAGE_CATALOG,
    )


@chat_call_routes.route("/chat/<sender_identifier>/<receiver_identifier>", methods=["GET", "POST"])
@login_required
def chat_page(sender_identifier, receiver_identifier):
    sender = find_user_by_identifier(sender_identifier)
    receiver = find_user_by_identifier(receiver_identifier)

    if sender is None or receiver is None:
        return "User not found", 404
    session_email = normalize_email(session.get("user_email", ""))
    if session_email != normalize_email(sender.email):
        log_security_event("chat_sender_mismatch", session_email, f"target={sender.email}")
        abort(403)

    ui = translation_bundle(get_current_language(sender))

    can_write, block_title, block_text = get_message_permission_status(sender, receiver)
    if not can_write:
        log_security_event("chat_permission_blocked", sender.email, f"Blocked chat attempt to {receiver.email}: {block_title}")
        return simple_page(block_title, block_text, sender.email)

    sender_restricted_receiver = is_restricted(sender.email, receiver.email)
    receiver_restricted_sender = is_restricted(receiver.email, sender.email)

    if receiver_restricted_sender:
        log_security_event("chat_restricted_blocked", sender.email, f"Restricted chat attempt to {receiver.email}")
        return simple_page(
            ui.get("messages_unavailable", "Messages unavailable"),
            ui.get("messages_restricted_intro", "This user limited communication with you."),
            sender.email
        )

    # --- Typing status logic ---
    typing_data = load_typing_status()
    typing_key = f"{receiver.email}->{sender.email}"
    receiver_typing = False
    if typing_key in typing_data:
        last_typing = typing_data.get(typing_key, 0)
        if datetime.now().timestamp() - last_typing < 4:
            receiver_typing = True

    presence_data = load_presence_status()
    presence_data[sender.email] = datetime.now().timestamp()
    save_presence_status(presence_data)
    receiver_status_text = format_visible_last_seen(sender.email, receiver.email, presence_data.get(receiver.email))
    typing_status_text = f"✍️ {safe_text(ui.get('typing_message', 'typing...'))}"


    messages = load_messages()
    changed = False

    for index, msg in enumerate(messages):
        if "id" not in msg:
            msg["id"] = index + 1
            changed = True

        if msg.get("to") == sender.email and msg.get("from") == receiver.email and msg.get("status") != "read":
            msg["status"] = "read"
            changed = True

    if changed:
        save_messages(messages)

    if request.method == "POST":
        validate_csrf_token()
        text = request.form.get("message", "").strip()
        reply_to = request.form.get("reply_to", "").strip()
        edit_message_id = request.form.get("edit_message_id", "").strip()
        file = request.files.get("media")

        if edit_message_id and text:
            for msg in messages:
                if str(msg.get("id")) == edit_message_id and msg.get("from") == sender.email:
                    msg["message"] = text
                    msg["edited"] = True
                    msg["edited_time"] = datetime.now().strftime("%d.%m.%Y %H:%M")
                    msg["source_language"] = detect_content_language(text)
                    msg["translations"] = {}
                    break

            save_messages(messages)
            return redirect(f"/chat/{sender.id}/{receiver.id}")

        media_url = ""
        media_type = ""
        media_name = ""

        if file and file.filename:
            original_filename = secure_filename(file.filename)
            ext = original_filename.rsplit(".", 1)[-1].lower()
            declared_mime = str(file.mimetype or "").split(";", 1)[0].lower()

            image_ext = ["jpg", "jpeg", "png", "webp", "gif"]
            video_ext = ["mp4", "mov", "webm", "m4v"]
            document_ext = ["pdf", "txt"]
            audio_ext = ["mp3", "wav", "m4a", "ogg", "webm"]

            if declared_mime.startswith("audio/") and ext in audio_ext:
                media_type = "audio"
            elif declared_mime.startswith("video/") and ext in video_ext:
                media_type = "video"
            elif declared_mime.startswith("image/") and ext in image_ext:
                media_type = "image"
            elif ext in video_ext:
                media_type = "video"
            elif ext in document_ext:
                media_type = "document"
            elif ext in audio_ext:
                media_type = "audio"
            else:
                return "Unsupported file type"

            if not allowed_mime_type(file):
                log_security_event("upload_rejected", sender.email, "Invalid chat media file content")
                return "Invalid file content", 400

            sender_id = secure_filename(str(sender.id))
            media_token = secrets.token_urlsafe(8)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            new_filename = f"chat_{sender_id}_{media_token}_{timestamp}.{ext}"
            upload_path = os.path.join(get_upload_folder(), new_filename)
            file.save(upload_path)

            media_url = f"/media-files/{new_filename}"
            media_name = original_filename

        if text != "" or media_url != "":
            next_id = 1
            if messages:
                next_id = max(int(msg.get("id", 0)) for msg in messages) + 1

            messages.append({
                "id": next_id,
                "from": sender.email,
                "to": receiver.email,
                "message": text,
                "media_url": media_url,
                "media_type": media_type,
                "media_name": media_name,
                "reply_to": reply_to,
                "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
                "status": "sent",
                "source_language": detect_content_language(text),
                "translations": {},
            })
            save_messages(messages)

        return redirect(f"/chat/{sender.id}/{receiver.id}")

    visible_messages = []

    for msg in messages:
        if msg.get("deleted_for_everyone") == True:
            continue

        if sender.email in msg.get("deleted_for", []):
            continue

        if (
            msg.get("from") == sender.email and msg.get("to") == receiver.email
        ) or (
            msg.get("from") == receiver.email and msg.get("to") == sender.email
        ):
            visible_messages.append(msg)

    translation_settings = normalize_user_ai_settings(sender.email)
    auto_translate_messages = translation_settings.get("auto_translate_messages") is True
    message_translation_language = str(translation_settings.get("message_translation_language", "auto"))
    if message_translation_language == "auto":
        message_translation_language = get_current_language(sender)
    message_translation_language = normalize_content_language_code(message_translation_language)
    if auto_translate_messages and get_ai_provider_status().get("enabled"):
        translation_batch = message_translation_service.auto_translate_incoming(
            visible_messages,
            sender.email,
            message_translation_language,
            normalize_content_language_code,
            translate_message_text,
            limit=20,
        )
        if translation_batch["changed"]:
            save_messages(messages)

    messages_by_id = {str(msg.get("id")): msg for msg in visible_messages}
    pinned_messages = []
    for msg in visible_messages:
        if msg.get("pinned") == True:
            pinned_messages.append(msg)

    pinned_view = None
    if pinned_messages:
        last_pinned = pinned_messages[-1]
        pinned_view = {
            "id": last_pinned.get("id"),
            "text": last_pinned.get("message", ui.get("media_file", "Media file")),
        }
    message_views = []

    for msg in visible_messages:
        css_class = "mine" if msg.get("from") == sender.email else "theirs"
        media_url = msg.get("media_url", "")
        media_type = msg.get("media_type", "")
        media_name = msg.get("media_name", "")
        msg_id = msg.get("id")
        call_event_view = None
        if media_type == "call_event" or msg.get("message_type") == "call_event":
            call_type = clean_text(msg.get("call_type", "audio"))
            call_event = clean_text(msg.get("call_event", "ended"))
            call_icon = "🎥" if call_type == "video" else "📞"
            call_title = ui.get("video_call", "Video call") if call_type == "video" else ui.get("audio_call", "Audio call")

            if call_event == "missed":
                call_status = ui.get("call_missed", "Missed")
            elif call_event == "declined":
                call_status = ui.get("call_declined", "Declined")
            elif call_event == "ended":
                call_status = ui.get("call_ended", "Ended")
            elif call_event == "accepted":
                call_status = ui.get("call_accepted", "Accepted")
            else:
                call_status = ui.get("call", "Call")

            call_duration = clean_text(msg.get("call_duration_text", ""))
            call_time = msg.get("time", "")
            call_meta = call_time
            if call_duration:
                call_meta = f"{call_time} · {call_duration}"
            call_event_view = {"icon": call_icon, "status": call_status, "title": call_title, "meta": call_meta}

        reply_view = None
        reply_id = str(msg.get("reply_to", ""))
        if reply_id and reply_id in messages_by_id:
            replied_msg = messages_by_id[reply_id]
            reply_view = {
                "author": ui.get("you", "You") if replied_msg.get("from") == sender.email else receiver.name,
                "text": replied_msg.get("message", ui.get("media_file", "Media file")),
            }

        message_text = "" if call_event_view else (msg.get("message", "") or "")
        translated_text = message_translation_service.cached_translation(
            msg, message_translation_language, normalize_content_language_code,
        ) if msg.get("to") == sender.email else ""
        if translated_text == msg.get("message", ""):
            translated_text = ""
        reactions = msg.get("reactions", {})
        message_views.append({
            "id": msg_id,
            "css_class": css_class,
            "mine": msg.get("from") == sender.email,
            "read": msg.get("status") == "read",
            "text": message_text,
            "time": msg.get("time", ""),
            "edited": msg.get("edited") is True,
            "forwarded": msg.get("forwarded") is True,
            "reply": reply_view,
            "media_url": media_url,
            "media_type": media_type,
            "media_name": media_name,
            "call_event": call_event_view,
            "translation": translated_text,
            "reactions": [
                {"emoji": emoji, "count": len(users_list)}
                for emoji, users_list in reactions.items()
            ],
        })

    chat_i18n = {
        "aiTranslationNotice": ui.get("ai_message_translation_notice", "AI message translation will be connected after API key setup."),
        "sentAt": ui.get("sent_at", "Sent:"),
        "incomingVideoCall": ui.get("incoming_video_call", "Incoming video call"),
        "incomingAudioCall": ui.get("incoming_audio_call", "Incoming audio call"),
        "user": ui.get("user", "User"),
        "isCallingYou": ui.get("is_calling_you", "is calling you"),
        "mediaFile": ui.get("media_file", "Media file"),
        "message": ui.get("message", "Message"),
        "messageSendError": ui.get("message_send_error", "Message could not be sent. Please try again."),
        "enterSearchText": ui.get("enter_search_text", "Enter text to search"),
        "searchNoResults": ui.get("search_no_results", "Nothing found"),
        "searchFound": ui.get("search_found", "Found"),
        "searchCurrent": ui.get("search_current", "current"),
        "voiceRecording": ui.get("voice_recording", "Recording voice message..."),
        "voiceNotSupported": ui.get("voice_not_supported", "Your browser does not support voice recording."),
        "microphoneError": ui.get("microphone_error", "Could not enable the microphone. Check browser permission."),
        "voiceSending": ui.get("voice_sending", "Voice message is being sent..."),
        "voiceSendError": ui.get("voice_send_error", "Could not send the voice message. Please try again."),
        "translatedMessage": ui.get("translated_message", "Translation"),
        "translationUnavailable": ui.get("translation_unavailable", "Translation is temporarily unavailable"),
        "draftSaved": ui.get("message_draft_saved", "Draft saved"),
        "draftRestored": ui.get("message_draft_restored", "Draft restored"),
        "offlineDraftSafe": ui.get("message_offline_draft_safe", "Offline — your draft is saved on this device"),
        "connectionRestored": ui.get("message_connection_restored", "Connection restored"),
    }
    chat_i18n_json = json.dumps(chat_i18n, ensure_ascii=False)
    chat_config = {
        "i18n": chat_i18n_json,
        "csrf_token": get_csrf_token(),
        "sender": sender.email,
        "receiver": receiver.email,
        "receiver_avatar": get_avatar_url(receiver.email),
        "translation_language": message_translation_language,
    }
    return render_template(
        "chat.html",
        ui=ui,
        sender=sender,
        receiver=receiver,
        receiver_avatar=get_avatar_url(receiver.email),
        typing_status=typing_status_text if receiver_typing else receiver_status_text,
        sender_restricted_receiver=sender_restricted_receiver,
        pinned=pinned_view,
        messages=message_views,
        reaction_choices=("❤️", "😂", "👍", "🔥", "😮"),
        config=chat_config,
        csrf_token_input=csrf_input(),
    )

@chat_call_routes.route("/react_message/<sender_email>/<receiver_email>/<int:message_id>/<emoji>", methods=["POST"])
@login_required
def react_message(sender_email, receiver_email, message_id, emoji):
    validate_csrf_token()
    messages = load_messages()

    for msg in messages:
        if msg.get("id") == message_id:
            same_chat = (
                (msg.get("from") == sender_email and msg.get("to") == receiver_email) or
                (msg.get("from") == receiver_email and msg.get("to") == sender_email)
            )

            if not same_chat:
                continue

            reactions = msg.get("reactions", {})

            for reaction_name in list(reactions.keys()):
                if sender_email in reactions.get(reaction_name, []):
                    reactions[reaction_name].remove(sender_email)
                    if len(reactions[reaction_name]) == 0:
                        del reactions[reaction_name]

            users_list = reactions.get(emoji, [])
            if sender_email not in users_list:
                users_list.append(sender_email)
                reactions[emoji] = users_list

            msg["reactions"] = reactions
            break

    save_messages(messages)
    return redirect(f"/chat/{sender_email}/{receiver_email}")


# New route for deleting a message
@chat_call_routes.route("/delete_message/<sender_email>/<receiver_email>/<int:message_id>/<mode>", methods=["POST"])
@login_required
def delete_message(sender_email, receiver_email, message_id, mode):
    validate_csrf_token()
    if mode not in {"me", "all"}:
        abort(404)
    messages = load_messages()

    for msg in messages:
        if msg.get("id") == message_id:
            same_chat = (
                (msg.get("from") == sender_email and msg.get("to") == receiver_email) or
                (msg.get("from") == receiver_email and msg.get("to") == sender_email)
            )

            if not same_chat:
                continue

            if mode == "me":
                deleted_for = msg.get("deleted_for", [])
                if sender_email not in deleted_for:
                    deleted_for.append(sender_email)
                msg["deleted_for"] = deleted_for

            elif mode == "all" and msg.get("from") == sender_email:
                msg["deleted_for_everyone"] = True

            break

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{receiver_email}")

# --- Pin/unpin message routes ---
@chat_call_routes.route("/pin_message/<sender_email>/<receiver_email>/<int:message_id>", methods=["POST"])
@login_required
def pin_message(sender_email, receiver_email, message_id):
    validate_csrf_token()
    messages = load_messages()

    for msg in messages:
        same_chat = (
            (msg.get("from") == sender_email and msg.get("to") == receiver_email) or
            (msg.get("from") == receiver_email and msg.get("to") == sender_email)
        )

        if same_chat:
            msg["pinned"] = False

        if msg.get("id") == message_id:
            msg["pinned"] = True

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{receiver_email}")


@chat_call_routes.route("/unpin_message/<sender_email>/<receiver_email>/<int:message_id>", methods=["POST"])
@login_required
def unpin_message(sender_email, receiver_email, message_id):
    validate_csrf_token()
    messages = load_messages()

    for msg in messages:
        if msg.get("id") == message_id:
            msg["pinned"] = False
            break

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{receiver_email}")

# --- Forward message select route ---
@chat_call_routes.route("/forward_message_select/<sender_email>/<receiver_email>/<int:message_id>")
@login_required
def forward_message_select(sender_email, receiver_email, message_id):
    current_user = find_user_by_email(sender_email)

    if current_user is None:
        return "User not found", 404

    messages = load_messages()
    original_message = next(
        (
            message for message in messages
            if isinstance(message, dict)
            and message.get("id") == message_id
            and sender_email in {message.get("from"), message.get("to")}
        ),
        None,
    )
    if original_message is None:
        return "Message not found", 404

    ui = translation_bundle(get_current_language(current_user))
    language = ui.get("language_code", "en")
    copy = {
        "ru": {"title": "Переслать сообщение", "back": "Назад в чат", "send": "Отправить", "empty": "Нет доступных получателей."},
        "de": {"title": "Nachricht weiterleiten", "back": "Zurück zum Chat", "send": "Senden", "empty": "Keine Empfänger verfügbar."},
        "en": {"title": "Forward message", "back": "Back to chat", "send": "Send", "empty": "No recipients available."},
        "tr": {"title": "Mesajı ilet", "back": "Sohbete dön", "send": "Gönder", "empty": "Uygun alıcı yok."},
    }.get(language, {"title": ui.get("forward", "Forward message"), "back": ui.get("back", "Back"), "send": ui.get("send", "Send"), "empty": "No recipients available."})
    recipients = [
        {"email": user.email, "name": user.name, "profession": user.profession}
        for user in get_users()
        if normalize_email(user.email) != normalize_email(sender_email)
        and not is_blocked(user.email, sender_email)
        and not is_blocked(sender_email, user.email)
    ]

    return render_template(
        "forward_message.html",
        ui=ui,
        copy=copy,
        email=current_user.email,
        sender_email=current_user.email,
        receiver_email=receiver_email,
        message_id=message_id,
        recipients=recipients,
        csrf_token_input=csrf_input(),
    )


# --- Forward message action route ---
@chat_call_routes.route("/forward_message/<sender_email>/<int:message_id>/<target_email>", methods=["POST"])
@login_required
def forward_message(sender_email, message_id, target_email):
    validate_csrf_token()
    messages = load_messages()
    target_user = find_user_by_email(target_email)
    if target_user is None or normalize_email(target_email) == normalize_email(sender_email):
        abort(404)
    if is_blocked(target_email, sender_email) or is_blocked(sender_email, target_email):
        abort(403)

    original_message = None

    for msg in messages:
        if (
            isinstance(msg, dict)
            and msg.get("id") == message_id
            and sender_email in {msg.get("from"), msg.get("to")}
        ):
            original_message = msg
            break

    if original_message is None:
        return "Message not found", 404

    next_id = 1
    if messages:
        next_id = max(int(m.get("id", 0)) for m in messages) + 1

    messages.append({
        "id": next_id,
        "from": sender_email,
        "to": target_email,
        "message": original_message.get("message", ""),
        "media_url": original_message.get("media_url", ""),
        "media_type": original_message.get("media_type", ""),
        "media_name": original_message.get("media_name", ""),
        "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "status": "sent",
        "forwarded": True
    })

    save_messages(messages)

    return redirect(f"/chat/{sender_email}/{target_email}", code=303)
