from flask import Blueprint, jsonify


def create_mobile_api(deps):
    api = Blueprint("mobile_bootstrap_api", __name__)

    @api.route("/api/mobile/bootstrap", methods=["GET"])
    def bootstrap():
        user = deps["get_api_current_user"]()
        if user is None:
            return jsonify({"ok": False, "error": "authentication_required"}), 401
        settings = deps["normalize_user_ai_settings"](user.email)
        return jsonify({
            "ok": True,
            "api_version": 1,
            "user": deps["api_user_payload"](user),
            "features": {
                "audio_calls": True, "video_calls": True, "call_push": True,
                "live_call_captions": settings.get("live_call_captions") is True,
                "server_transcription_consent": settings.get("allow_server_call_transcription") is True,
                "ai_voice_translation_consent": settings.get("allow_ai_voice_translation") is True,
                "auto_translate_call_captions": settings.get("auto_translate_call_captions") is True,
                "auto_translate_messages": settings.get("auto_translate_messages") is True,
                "translation_provider_available": deps["translation_provider_available"](),
                "transcription_provider_available": deps["transcription_provider_available"](),
                "realtime_speech_provider_available": deps["realtime_speech_provider_available"](),
            },
            "languages": {
                "ui": deps["get_current_language"](user),
                "message_target": settings.get("message_translation_language", "auto"),
                "call_spoken": settings.get("call_spoken_language", "auto"),
                "call_caption_target": settings.get("call_caption_language", "auto"),
            },
            "call_contract": {
                "room_endpoint": "/api/calls/room",
                "incoming_context_endpoint_template": "/api/calls/{call_id}/context",
                "signals_endpoint_template": "/api/calls/{call_id}/signals",
                "ack_endpoint_template": "/api/calls/{call_id}/signals/ack",
                "ice_endpoint_template": "/api/calls/{call_id}/ice-servers",
                "captions_endpoint_template": "/api/calls/{call_id}/captions",
                "realtime_session_endpoint_template": "/api/calls/{call_id}/translation/realtime-session",
                "translated_speech_endpoint_template": "/api/calls/{call_id}/captions/{caption_id}/speech",
                "signal_event_id_min_length": 16,
                "signal_event_id_max_length": 80,
                "ack_batch_max": 50,
                "ringing_timeout_seconds": 45,
                "negotiation_timeout_seconds": 30,
            },
            "speech_translation_contract": deps["build_mobile_speech_contract"](),
        })

    return api
