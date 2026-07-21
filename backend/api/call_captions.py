import secrets
import time

from flask import Blueprint, Response, jsonify, request


def create_call_captions_api(deps):
    api = Blueprint("call_captions_api", __name__)

    def error(message, status=400, headers=None):
        response = jsonify({"ok": False, "error": deps["clean_text"](message)})
        response.status_code = status
        for name, value in (headers or {}).items():
            response.headers[name] = str(value)
        return response

    def context(call_id):
        user = deps["get_api_current_user"]()
        if user is None:
            return None, None, None, error("Authentication required", 401)
        if (
            request.method == "POST"
            and request.path.endswith("/captions/transcribe")
            and request.content_length is not None
            and request.content_length > deps["speech_transcription_service"].MAX_TRANSCRIPTION_REQUEST_BYTES
        ):
            return None, None, None, error("Transcription request too large", 413)
        if request.method == "POST":
            data = (request.get_json(silent=True) or {}) if request.is_json else request.form
        else:
            data = request.args
        other_email = deps["normalize_email"](data.get("other_email", ""))
        call_type = deps["clean_text"](data.get("call_type", ""))
        if call_type not in {"audio", "video"} or not other_email:
            return None, None, None, error("Invalid call context", 400)
        other = deps["find_user_by_email"](other_email)
        if other is None:
            return None, None, None, error("User not found", 404)
        expected = deps["get_call_room_id"](user.email, other.email, call_type)
        if not secrets.compare_digest(deps["secure_call_id"](call_id), expected):
            return None, None, None, error("Forbidden call room", 403)
        if deps["is_blocked"](user.email, other.email) or deps["is_blocked"](other.email, user.email):
            return None, None, None, error("Call unavailable", 403)
        if deps["is_restricted"](user.email, other.email) or deps["is_restricted"](other.email, user.email):
            return None, None, None, error("Call unavailable", 403)
        return user, other, data, None

    @api.route("/api/calls/<call_id>/captions", methods=["GET", "POST"])
    def captions(call_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        settings = deps["normalize_user_ai_settings"](user.email)
        if settings.get("live_call_captions") is not True:
            return error("Live captions are disabled", 403)

        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        room = deps["get_call_signal_room"](room_id)
        if not isinstance(room, dict) or room.get("status") not in {"active", "accepted", "ringing"}:
            return error("Call is not active", 409)

        if request.method == "POST":
            text = deps["call_caption_service"].clean_segment(data.get("text", ""), deps["clean_text"])
            if not text:
                return error("Caption text is required", 400)
            try:
                sequence = max(int(data.get("sequence", 0) or 0), 0)
            except (TypeError, ValueError):
                return error("Invalid caption sequence", 400)
            segment = {
                "id": secrets.token_urlsafe(10),
                "speaker_email": deps["normalize_email"](user.email),
                "text": text,
                "source_language": deps["normalize_content_language_code"](
                    data.get("source_language") or deps["detect_content_language"](text)
                ),
                "is_final": data.get("is_final") is True,
                "sequence": sequence,
                "created_at": time.time(),
                "translations": {},
            }
            append_status = deps["append_call_caption"](
                room_id,
                segment,
                max_items=deps["call_caption_service"].MAX_ROOM_CAPTIONS,
                minimum_created_at=time.time() - deps["call_caption_service"].CAPTION_TTL_SECONDS,
            )
            if append_status != "appended":
                return error("Call is not active", 409)
            return jsonify({"ok": True, "caption": segment}), 201

        captions = deps["call_caption_service"].segments_after(
            room, data.get("after", 0), exclude_email=user.email,
        )
        return jsonify({"ok": True, "captions": captions, "server_time": time.time()})

    @api.route("/api/calls/<call_id>/ice-servers", methods=["GET"])
    def ice_servers(call_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        cache_key = f"{deps['normalize_email'](user.email)}::{room_id}"
        configuration = deps["turn_credential_service"].get_ice_configuration(cache_key)
        response = jsonify({"ok": True, **configuration})
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        return response

    @api.route("/api/calls/<call_id>/quality", methods=["POST"])
    def call_quality(call_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        room = deps["get_call_signal_room"](room_id)
        if not isinstance(room, dict) or room.get("status") not in {"active", "accepted", "ringing"}:
            return error("Call is not active", 409)
        sample = deps["call_quality_service"].normalize_sample(data, user.email, time.time())
        append_status = deps["append_call_quality_sample"](
            room_id, sample, max_items=deps["call_quality_service"].MAX_QUALITY_SAMPLES, minimum_interval=4,
        )
        if append_status == "rate_limited":
            return error("Quality sample rate limit exceeded", 429, {"Retry-After": "4"})
        if append_status != "appended":
            return error("Call is not active", 409)
        return jsonify({"ok": True, "quality": sample["quality"]}), 201

    @api.route("/api/calls/<call_id>/captions/<caption_id>/translation", methods=["POST"])
    def caption_translation(call_id, caption_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        settings = deps["normalize_user_ai_settings"](user.email)
        if settings.get("live_call_captions") is not True:
            return error("Live captions are disabled", 403)
        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        room = deps["get_call_signal_room"](room_id)
        if not isinstance(room, dict):
            return error("Call is not active", 409)
        caption = deps["call_caption_service"].caption_by_id(room, caption_id)
        if caption is None:
            return error("Caption not found", 404)

        target_language = data.get("target_language") or settings.get("call_caption_language", "auto")
        if target_language == "auto":
            target_language = deps["get_current_language"](user)
        result = deps["message_translation_service"].translate_message(
            {"message": caption.get("text", ""), "source_language": caption.get("source_language", "unknown"),
             "translations": caption.get("translations", {})},
            target_language,
            deps["normalize_content_language_code"],
            deps["translate_message_text"],
        )
        if not result.get("ok"):
            return error(result.get("error", "translation_unavailable"), 503)
        if not result.get("cached"):
            update_status = deps["set_call_caption_translation"](
                room_id, caption_id, result["target_language"], result["translated_text"],
            )
            if update_status != "updated":
                return error("Caption not found", 404)
        return jsonify({"ok": True, "translation": result})

    @api.route("/api/calls/<call_id>/captions/transcribe", methods=["POST"])
    def transcribe_caption(call_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        settings = deps["normalize_user_ai_settings"](user.email)
        if settings.get("live_call_captions") is not True:
            return error("Live captions are disabled", 403)
        if settings.get("allow_server_call_transcription") is not True:
            return error("Server transcription consent is required", 403)
        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        room = deps["get_call_signal_room"](room_id)
        if not isinstance(room, dict) or room.get("status") not in {"active", "accepted", "ringing"}:
            return error("Call is not active", 409)
        audio_file = request.files.get("audio")
        if audio_file is None:
            return error("Audio chunk is required", 400)
        audio_bytes = audio_file.read(deps["speech_transcription_service"].MAX_AUDIO_CHUNK_BYTES + 1)
        language = deps["normalize_content_language_code"](data.get("source_language", ""))
        validation, validation_error = deps["speech_transcription_service"].validate_audio_chunk(audio_bytes, audio_file.mimetype)
        if validation_error:
            return error(validation_error, 400)
        try:
            sequence = int(data.get("sequence", 0) or 0)
        except (TypeError, ValueError):
            return error("Invalid caption sequence", 400)
        if sequence <= 0:
            return error("Invalid caption sequence", 400)
        reservation = deps["reserve_call_transcription"](
            room_id, user.email, sequence, time.time(), window_seconds=60, limit=18,
        )
        if reservation == "duplicate":
            return error("Duplicate audio chunk", 409)
        if reservation == "rate_limited":
            return error("Transcription rate limit exceeded", 429, {"Retry-After": "4"})
        if reservation != "reserved":
            return error("Call is not active", 409)
        result = deps["transcribe_audio_chunk"](audio_bytes, audio_file.mimetype, language)
        if not result.get("ok"):
            status = 400 if result.get("error") in {
                "unsupported_audio_type", "empty_audio_chunk", "audio_chunk_too_large", "invalid_audio_signature",
            } else 503
            return error(result.get("error", "transcription_unavailable"), status)
        text = deps["call_caption_service"].clean_segment(result.get("text", ""), deps["clean_text"])
        segment = {
            "id": secrets.token_urlsafe(10), "speaker_email": deps["normalize_email"](user.email),
            "text": text, "source_language": deps["normalize_content_language_code"](
                result.get("detected_language") or language
            ), "is_final": True,
            "sequence": sequence, "created_at": time.time(),
            "translations": {}, "transcription_model": result.get("model", ""),
        }
        append_status = deps["append_call_caption"](
            room_id, segment, max_items=deps["call_caption_service"].MAX_ROOM_CAPTIONS,
            minimum_created_at=time.time() - deps["call_caption_service"].CAPTION_TTL_SECONDS,
        )
        if append_status != "appended":
            return error("Call is not active", 409)
        return jsonify({"ok": True, "caption": segment}), 201

    @api.route("/api/calls/<call_id>/translation/realtime-session", methods=["POST"])
    def realtime_translation_session(call_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        settings = deps["normalize_user_ai_settings"](user.email)
        if settings.get("live_call_captions") is not True:
            return error("Live captions are disabled", 403)
        if settings.get("allow_server_call_transcription") is not True:
            return error("Server transcription consent is required", 403)
        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        room = deps["get_call_signal_room"](room_id)
        if not isinstance(room, dict) or room.get("status") not in {"active", "accepted"}:
            return error("Call is not active", 409)
        limiter_key = f"realtime-session::{deps['normalize_email'](user.email)}::{room_id}"
        if not deps["speech_rate_limiter"].allow(limiter_key):
            return error("Realtime session rate limit exceeded", 429, {"Retry-After": "10"})
        language = deps["normalize_content_language_code"](settings.get("call_spoken_language", "auto"))
        result = deps["create_realtime_transcription_session"](language)
        if not result.get("ok"):
            return error(result.get("error", "realtime_provider_unavailable"), 503)
        response = jsonify({"ok": True, "session": {
            "client_secret": result["client_secret"], "expires_at": result["expires_at"],
            "model": result["model"], "transport": result["transport"],
            "transcription_model": result.get("transcription_model", ""),
            "calls_endpoint": result["calls_endpoint"],
            "source_language": language or "auto",
        }})
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        return response

    @api.route("/api/calls/<call_id>/captions/<caption_id>/speech", methods=["POST"])
    def translated_caption_speech(call_id, caption_id):
        user, other, data, context_error = context(call_id)
        if context_error:
            return context_error
        settings = deps["normalize_user_ai_settings"](user.email)
        if settings.get("live_call_captions") is not True or settings.get("allow_ai_voice_translation") is not True:
            return error("AI voice translation consent is required", 403)
        room_id = deps["get_call_room_id"](user.email, other.email, data.get("call_type"))
        room = deps["get_call_signal_room"](room_id)
        if not isinstance(room, dict) or room.get("status") not in {"active", "accepted"}:
            return error("Call is not active", 409)
        caption = deps["call_caption_service"].caption_by_id(room, caption_id)
        if caption is None or deps["normalize_email"](caption.get("speaker_email")) == deps["normalize_email"](user.email):
            return error("Caption not found", 404)
        target_language = settings.get("call_caption_language", "auto")
        if target_language == "auto":
            target_language = deps["get_current_language"](user)
        translated = deps["message_translation_service"].translate_message(
            {"message": caption.get("text", ""), "source_language": caption.get("source_language", "unknown"),
             "translations": caption.get("translations", {})},
            target_language, deps["normalize_content_language_code"], deps["translate_message_text"],
        )
        if not translated.get("ok"):
            return error(translated.get("error", "translation_unavailable"), 503)
        if not translated.get("cached"):
            update_status = deps["set_call_caption_translation"](
                room_id, caption_id, translated["target_language"], translated["translated_text"],
            )
            if update_status != "updated":
                return error("Caption not found", 404)
        limiter_key = f"translated-speech::{deps['normalize_email'](user.email)}::{room_id}"
        if not deps["speech_rate_limiter"].allow(limiter_key):
            return error("Speech synthesis rate limit exceeded", 429, {"Retry-After": "10"})
        speech = deps["synthesize_translated_speech"](translated.get("translated_text", ""), data.get("voice", "coral"))
        if not speech.get("ok"):
            status = 400 if speech.get("error") in {"unsupported_speech_voice", "speech_text_too_long"} else 503
            return error(speech.get("error", "speech_provider_unavailable"), status)
        response = Response(speech["audio"], status=200, mimetype=speech["content_type"])
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-AI-Generated-Voice"] = "true"
        response.headers["X-AI-Voice"] = speech["voice"]
        response.headers["X-Caption-Id"] = caption_id
        response.headers["Content-Language"] = translated["target_language"]
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return api
