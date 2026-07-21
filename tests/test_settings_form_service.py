from backend.services import settings_form_service


def normalize_language(value):
    value = str(value or "").strip().lower()
    return {"en-us": "en"}.get(value, value)


def test_parse_privacy_ai_form_builds_settings_and_language():
    settings, language = settings_form_service.parse_privacy_ai_form(
        {
            "language": "en-US",
            "profile_visibility": "friends",
            "story_visibility": "close_friends",
            "message_permission": "verified",
            "ai_personalization_level": "high",
            "show_in_search": "on",
            "show_online_status": "on",
            "ai_memory_enabled": "on",
            "message_notifications": "on",
            "auto_translate_messages": "on",
            "message_translation_language": "tr",
            "live_call_captions": "on",
            "allow_server_call_transcription": "on",
            "auto_translate_call_captions": "on",
            "call_caption_language": "en",
            "call_spoken_language": "tr",
        },
        normalize_language,
        {"en": "English", "tr": "Turkish"},
    )

    assert language == "en"
    assert settings["profile_visibility"] == "friends"
    assert settings["story_visibility"] == "close_friends"
    assert settings["message_permission"] == "verified"
    assert settings["ai_personalization_level"] == "high"
    assert settings["show_in_search"] is True
    assert settings["show_online_status"] is True
    assert settings["ai_memory_enabled"] is True
    assert settings["message_notifications"] is True
    assert settings["auto_translate_messages"] is True
    assert settings["message_translation_language"] == "tr"
    assert settings["live_call_captions"] is True
    assert settings["allow_server_call_transcription"] is True
    assert settings["auto_translate_call_captions"] is True
    assert settings["call_caption_language"] == "en"
    assert settings["call_spoken_language"] == "tr"
    assert settings["two_factor_required"] is False


def test_parse_privacy_ai_form_falls_back_for_invalid_selects_and_language():
    settings, language = settings_form_service.parse_privacy_ai_form(
        {
            "language": "xx",
            "profile_visibility": "bad",
            "story_visibility": "bad",
            "message_permission": "bad",
            "ai_personalization_level": "bad",
            "message_translation_language": "xx",
            "call_spoken_language": "xx",
        },
        normalize_language,
        {"en": "English"},
    )

    assert language == ""
    assert settings["profile_visibility"] == "public"
    assert settings["story_visibility"] == "friends"
    assert settings["message_permission"] == "everyone"
    assert settings["ai_personalization_level"] == "balanced"
    assert settings["message_translation_language"] == "auto"
    assert settings["call_spoken_language"] == "auto"
