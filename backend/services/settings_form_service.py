BOOLEAN_SETTING_FIELDS = [
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
    "auto_translate_messages",
    "live_call_captions",
    "allow_server_call_transcription",
    "allow_ai_voice_translation",
    "auto_translate_call_captions",
]

MESSAGE_PERMISSIONS = {"everyone", "friends", "verified", "none"}
PROFILE_VISIBILITIES = {"public", "friends", "private"}
STORY_VISIBILITIES = {"everyone", "friends", "close_friends", "none"}
AI_PERSONALIZATION_LEVELS = {"minimal", "balanced", "high"}


def _form_get(form, key, default=""):
    if hasattr(form, "get"):
        return form.get(key, default)
    return default


def parse_privacy_ai_form(form, normalize_language_code, supported_languages):
    message_permission = _form_get(form, "message_permission", "everyone")
    if message_permission not in MESSAGE_PERMISSIONS:
        message_permission = "everyone"

    profile_visibility = _form_get(form, "profile_visibility", "public")
    if profile_visibility not in PROFILE_VISIBILITIES:
        profile_visibility = "public"

    story_visibility = _form_get(form, "story_visibility", "friends")
    if story_visibility not in STORY_VISIBILITIES:
        story_visibility = "friends"

    ai_personalization_level = _form_get(form, "ai_personalization_level", "balanced")
    if ai_personalization_level not in AI_PERSONALIZATION_LEVELS:
        ai_personalization_level = "balanced"

    language = normalize_language_code(_form_get(form, "language", ""))
    if language not in supported_languages:
        language = ""

    translation_language = _form_get(form, "message_translation_language", "auto").strip().lower()
    if translation_language != "auto" and translation_language not in supported_languages:
        translation_language = "auto"
    caption_language = _form_get(form, "call_caption_language", "auto").strip().lower()
    if caption_language != "auto" and caption_language not in supported_languages:
        caption_language = "auto"
    spoken_language = _form_get(form, "call_spoken_language", "auto").strip().lower()
    if spoken_language != "auto" and spoken_language not in supported_languages:
        spoken_language = "auto"

    settings = {
        field_name: _form_get(form, field_name) == "on"
        for field_name in BOOLEAN_SETTING_FIELDS
    }
    settings.update({
        "message_permission": message_permission,
        "profile_visibility": profile_visibility,
        "story_visibility": story_visibility,
        "ai_personalization_level": ai_personalization_level,
        "message_translation_language": translation_language,
        "call_caption_language": caption_language,
        "call_spoken_language": spoken_language,
    })

    return settings, language
