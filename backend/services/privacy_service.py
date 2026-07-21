from backend.i18n import LANGUAGE_CATALOG


DEFAULT_SETTINGS = {
    "show_in_search": True,
    "allow_messages": True,
    "private_profile": False,
    "show_online_status": True,
    "show_activity_status": True,
    "allow_profile_indexing": True,
    "ai_recommendations": True,
    "ai_life_radar": True,
    "recommend_my_profile": True,
    "ai_activity_analysis": True,
    "ai_memory_enabled": True,
    "ai_feed_learning": True,
    "ai_match_explanations": True,
    "notifications_enabled": True,
    "message_notifications": True,
    "match_notifications": True,
    "friend_request_notifications": True,
    "product_update_notifications": False,
    "login_alerts": True,
    "two_factor_required": False,
    "sensitive_content_filter": True,
    "adult_content_filter": True,
    "autoplay_video": True,
    "download_data_ready": False,
    "account_deactivated": False,
    "auto_translate_messages": False,
    "message_translation_language": "auto",
    "live_call_captions": False,
    "allow_server_call_transcription": False,
    "allow_ai_voice_translation": False,
    "auto_translate_call_captions": False,
    "call_caption_language": "auto",
    "call_spoken_language": "auto",
    "message_permission": "everyone",
    "profile_visibility": "public",
    "story_visibility": "friends",
    "ai_personalization_level": "balanced",
}

BOOLEAN_KEYS = {
    "show_in_search",
    "private_profile",
    "show_online_status",
    "show_activity_status",
    "allow_profile_indexing",
    "ai_recommendations",
    "ai_life_radar",
    "recommend_my_profile",
    "ai_activity_analysis",
    "ai_memory_enabled",
    "ai_feed_learning",
    "ai_match_explanations",
    "notifications_enabled",
    "message_notifications",
    "match_notifications",
    "friend_request_notifications",
    "product_update_notifications",
    "login_alerts",
    "two_factor_required",
    "sensitive_content_filter",
    "adult_content_filter",
    "autoplay_video",
    "download_data_ready",
    "account_deactivated",
    "auto_translate_messages",
    "live_call_captions",
    "allow_server_call_transcription",
    "allow_ai_voice_translation",
    "auto_translate_call_captions",
}

MESSAGE_PERMISSIONS = {"everyone", "friends", "verified", "none"}
PROFILE_VISIBILITIES = {"public", "friends", "private"}
STORY_VISIBILITIES = {"everyone", "friends", "close_friends", "none"}
AI_PERSONALIZATION_LEVELS = {"minimal", "balanced", "high"}
TRANSLATION_LANGUAGE_VALUES = {"auto", *LANGUAGE_CATALOG.keys()}


def normalize_settings(settings=None):
    settings = settings if isinstance(settings, dict) else {}
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings)

    if merged.get("allow_messages") is False:
        merged["message_permission"] = "none"
    elif merged.get("verified_only_messages") is True:
        merged["message_permission"] = "verified"
    elif merged.get("friends_only_messages") is True:
        merged["message_permission"] = "friends"
    else:
        merged["message_permission"] = merged.get("message_permission", "everyone")

    if merged["message_permission"] not in MESSAGE_PERMISSIONS:
        merged["message_permission"] = "everyone"

    if merged.get("profile_visibility") not in PROFILE_VISIBILITIES:
        merged["profile_visibility"] = "public"

    if merged.get("story_visibility") not in STORY_VISIBILITIES:
        merged["story_visibility"] = "friends"

    if merged.get("ai_personalization_level") not in AI_PERSONALIZATION_LEVELS:
        merged["ai_personalization_level"] = "balanced"

    translation_language = str(merged.get("message_translation_language", "auto")).strip().lower()
    merged["message_translation_language"] = translation_language or "auto"
    caption_language = str(merged.get("call_caption_language", "auto")).strip().lower()
    merged["call_caption_language"] = caption_language if caption_language in TRANSLATION_LANGUAGE_VALUES else "auto"
    spoken_language = str(merged.get("call_spoken_language", "auto")).strip().lower()
    merged["call_spoken_language"] = spoken_language if spoken_language in TRANSLATION_LANGUAGE_VALUES else "auto"

    return merged


def build_update(current_settings, data):
    current_settings = normalize_settings(current_settings)
    data = data if isinstance(data, dict) else {}
    new_settings = {}

    for key in BOOLEAN_KEYS:
        if key in data:
            new_settings[key] = bool(data.get(key))

    if "message_permission" in data:
        message_permission = str(data.get("message_permission", "everyone")).strip()
        if message_permission not in MESSAGE_PERMISSIONS:
            return None, "Invalid message permission"
        new_settings["message_permission"] = message_permission

    if "profile_visibility" in data:
        profile_visibility = str(data.get("profile_visibility", "public")).strip()
        if profile_visibility not in PROFILE_VISIBILITIES:
            return None, "Invalid profile visibility"
        new_settings["profile_visibility"] = profile_visibility

    if "story_visibility" in data:
        story_visibility = str(data.get("story_visibility", "friends")).strip()
        if story_visibility not in STORY_VISIBILITIES:
            return None, "Invalid story visibility"
        new_settings["story_visibility"] = story_visibility

    if "ai_personalization_level" in data:
        ai_personalization_level = str(data.get("ai_personalization_level", "balanced")).strip()
        if ai_personalization_level not in AI_PERSONALIZATION_LEVELS:
            return None, "Invalid AI personalization level"
        new_settings["ai_personalization_level"] = ai_personalization_level

    if "message_translation_language" in data:
        translation_language = str(data.get("message_translation_language", "auto")).strip().lower()
        if translation_language not in TRANSLATION_LANGUAGE_VALUES:
            return None, "Invalid message translation language"
        new_settings["message_translation_language"] = translation_language

    if "call_caption_language" in data:
        caption_language = str(data.get("call_caption_language", "auto")).strip().lower()
        if caption_language not in TRANSLATION_LANGUAGE_VALUES:
            return None, "Invalid call caption language"
        new_settings["call_caption_language"] = caption_language

    if "call_spoken_language" in data:
        spoken_language = str(data.get("call_spoken_language", "auto")).strip().lower()
        if spoken_language not in TRANSLATION_LANGUAGE_VALUES:
            return None, "Invalid call spoken language"
        new_settings["call_spoken_language"] = spoken_language

    current_settings.update(new_settings)
    current_settings["allow_messages"] = current_settings.get("message_permission") != "none"
    current_settings["verified_only_messages"] = current_settings.get("message_permission") == "verified"
    current_settings["friends_only_messages"] = current_settings.get("message_permission") == "friends"
    return current_settings, ""


def apply_server_transcription_consent_metadata(previous_settings, next_settings, now_text):
    previous_settings = previous_settings if isinstance(previous_settings, dict) else {}
    next_settings = dict(next_settings) if isinstance(next_settings, dict) else {}
    was_allowed = previous_settings.get("allow_server_call_transcription") is True
    is_allowed = next_settings.get("allow_server_call_transcription") is True
    transition = ""
    if is_allowed and not was_allowed:
        next_settings["server_transcription_consent_at"] = str(now_text)
        next_settings["server_transcription_consent_revoked_at"] = ""
        transition = "granted"
    elif not is_allowed and was_allowed:
        next_settings["server_transcription_consent_at"] = str(
            previous_settings.get("server_transcription_consent_at", "")
        )
        next_settings["server_transcription_consent_revoked_at"] = str(now_text)
        transition = "revoked"
    return next_settings, transition


def apply_ai_voice_consent_metadata(previous_settings, next_settings, now_text):
    previous_settings = previous_settings if isinstance(previous_settings, dict) else {}
    next_settings = dict(next_settings) if isinstance(next_settings, dict) else {}
    was_allowed = previous_settings.get("allow_ai_voice_translation") is True
    is_allowed = next_settings.get("allow_ai_voice_translation") is True
    transition = ""
    if is_allowed and not was_allowed:
        next_settings["ai_voice_translation_consent_at"] = str(now_text)
        next_settings["ai_voice_translation_consent_revoked_at"] = ""
        transition = "granted"
    elif not is_allowed and was_allowed:
        next_settings["ai_voice_translation_consent_at"] = str(
            previous_settings.get("ai_voice_translation_consent_at", "")
        )
        next_settings["ai_voice_translation_consent_revoked_at"] = str(now_text)
        transition = "revoked"
    return next_settings, transition
