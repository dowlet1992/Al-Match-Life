from backend.models import User
from backend.services import privacy_service, profile_service


def test_profile_service_onboarding_and_update_profile():
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    assert profile_service.user_needs_onboarding(user) is True

    profile_service.apply_onboarding(
        user,
        {
            "looking_for": "team",
            "profession": "Founder",
            "goals": "startup, growth",
            "interests": "AI, product",
            "skills": "strategy, sales",
            "languages": "English, German",
        },
    )

    assert user.onboarding_completed is True
    assert user.looking_for == "team"
    assert user.goals == ["startup", "growth"]
    assert profile_service.user_needs_onboarding(user) is False

    profile_service.update_profile(user, {"bio": "<b>Hello</b>", "skills": ["AI", "sales"]})
    assert user.bio == "Hello"
    assert user.skills == ["AI", "sales"]


def test_profile_service_skip_onboarding():
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    profile_service.skip_onboarding(user)

    assert user.onboarding_skipped is True
    assert user.onboarding_completed is False
    assert profile_service.user_needs_onboarding(user) is False


def test_privacy_service_normalize_and_build_update():
    settings = privacy_service.normalize_settings({"allow_messages": False})

    assert settings["message_permission"] == "none"

    updated, error = privacy_service.build_update(
        settings,
        {"show_in_search": False, "message_permission": "friends"},
    )

    assert error == ""
    assert updated["show_in_search"] is False
    assert updated["message_permission"] == "friends"
    assert updated["allow_messages"] is True
    assert updated["friends_only_messages"] is True


def test_privacy_service_rejects_invalid_message_permission():
    updated, error = privacy_service.build_update({}, {"message_permission": "bad"})

    assert updated is None
    assert error == "Invalid message permission"


def test_privacy_service_validates_auto_translation_settings():
    updated, error = privacy_service.build_update({}, {
        "auto_translate_messages": True,
        "message_translation_language": "de",
    })

    assert error == ""
    assert updated["auto_translate_messages"] is True
    assert updated["message_translation_language"] == "de"

    rejected, error = privacy_service.build_update({}, {"message_translation_language": "zz"})
    assert rejected is None
    assert error == "Invalid message translation language"


def test_privacy_service_validates_call_caption_translation_language():
    updated, error = privacy_service.build_update({}, {
        "live_call_captions": True,
        "allow_server_call_transcription": True,
        "auto_translate_call_captions": True,
        "call_caption_language": "en",
        "call_spoken_language": "tr",
    })
    assert error == ""
    assert updated["call_caption_language"] == "en"
    assert updated["call_spoken_language"] == "tr"
    assert updated["allow_server_call_transcription"] is True

    rejected, error = privacy_service.build_update({}, {"call_caption_language": "zz"})
    assert rejected is None
    assert error == "Invalid call caption language"

    rejected, error = privacy_service.build_update({}, {"call_spoken_language": "zz"})
    assert rejected is None
    assert error == "Invalid call spoken language"


def test_server_transcription_consent_metadata_tracks_grant_and_revoke_once():
    granted, transition = privacy_service.apply_server_transcription_consent_metadata(
        {"allow_server_call_transcription": False},
        {"allow_server_call_transcription": True},
        "2026-07-20T10:00:00+00:00",
    )
    unchanged, unchanged_transition = privacy_service.apply_server_transcription_consent_metadata(
        granted, dict(granted), "2026-07-20T11:00:00+00:00",
    )
    revoked, revoke_transition = privacy_service.apply_server_transcription_consent_metadata(
        granted, {**granted, "allow_server_call_transcription": False},
        "2026-07-20T12:00:00+00:00",
    )

    assert transition == "granted"
    assert granted["server_transcription_consent_at"] == "2026-07-20T10:00:00+00:00"
    assert unchanged_transition == ""
    assert unchanged["server_transcription_consent_at"] == granted["server_transcription_consent_at"]
    assert revoke_transition == "revoked"
    assert revoked["server_transcription_consent_at"] == granted["server_transcription_consent_at"]
    assert revoked["server_transcription_consent_revoked_at"] == "2026-07-20T12:00:00+00:00"


def test_ai_voice_consent_metadata_tracks_grant_and_revoke():
    granted, transition = privacy_service.apply_ai_voice_consent_metadata(
        {"allow_ai_voice_translation": False},
        {"allow_ai_voice_translation": True},
        "2026-07-20T10:00:00+00:00",
    )
    revoked, revoke_transition = privacy_service.apply_ai_voice_consent_metadata(
        granted, {**granted, "allow_ai_voice_translation": False},
        "2026-07-20T12:00:00+00:00",
    )
    assert transition == "granted"
    assert granted["ai_voice_translation_consent_at"] == "2026-07-20T10:00:00+00:00"
    assert revoke_transition == "revoked"
    assert revoked["ai_voice_translation_consent_revoked_at"] == "2026-07-20T12:00:00+00:00"
