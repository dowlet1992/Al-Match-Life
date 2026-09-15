import app
from backend.i18n import LANGUAGE_CATALOG, SUPPORTED_LANGUAGES
from pathlib import Path


def test_app_language_catalogs_use_i18n_single_source_of_truth():
    assert app.SUPPORTED_LANGUAGES == SUPPORTED_LANGUAGES
    assert app.CONTENT_LANGUAGES["km"] == "ភាសាខ្មែរ"
    assert app.CONTENT_LANGUAGES["mn"] == "Монгол"
    assert app.CONTENT_LANGUAGES["pa"] == "ਪੰਜਾਬੀ"
    assert app.CONTENT_LANGUAGES["te"] == "తెలుగు"
    assert set(LANGUAGE_CATALOG).issubset(set(app.CONTENT_LANGUAGES))


def test_app_ui_translations_cover_all_supported_languages():
    required_keys = set(app.UI_TRANSLATIONS[app.DEFAULT_LANGUAGE].keys())

    assert set(app.SUPPORTED_LANGUAGES).issubset(set(app.UI_TRANSLATIONS))
    for language in app.SUPPORTED_LANGUAGES:
        assert required_keys - set(app.UI_TRANSLATIONS[language]) == set()


def test_web_interface_exposes_only_the_maintained_language_set():
    assert app.UI_LANGUAGES == app.SUPPORTED_LANGUAGES
    assert app.t("create_post", "ru") == app.translation_bundle("ru")["create_post"]
    assert app.t("create_post", "en") == app.translation_bundle("en")["create_post"]
    assert app.t("create_post", "de") == app.translation_bundle("de")["create_post"]


def test_call_and_video_runtime_messages_are_translated_in_all_ui_languages():
    keys = {
        "call_in_progress", "call_reconnect_failed", "offline_waiting",
        "reconnecting_attempt", "captions_disabled_help", "connecting",
        "requesting_media_access", "connection_interrupted", "call_ended",
        "waiting_for_answer", "joining_incoming_call", "media_access_denied",
        "offline_call_recovery", "video_paused", "video_playing",
        "video_tap_to_play",
    }

    for language in app.UI_LANGUAGES:
        bundle = app.translation_bundle(language)
        assert all(bundle[key] and bundle[key] != key for key in keys)


def test_discovery_templates_do_not_hardcode_translatable_headings():
    feed_template = Path("frontend/feed.html").read_text(encoding="utf-8")
    matches_template = Path("frontend/matches.html").read_text(encoding="utf-8")
    register_template = Path("frontend/register.html").read_text(encoding="utf-8")

    assert '>Smart feed<' not in feed_template
    assert '>💡 Idea<' not in feed_template
    assert '<h1>🤝 AI Matches</h1>' not in matches_template
    assert 'aria-label="Код страны"' not in register_template


def test_discovery_headings_are_translated_in_all_ui_languages():
    keys = {"ai_discover", "smart_feed", "idea", "project", "achievement", "country_code"}

    for language in app.UI_LANGUAGES:
        bundle = app.translation_bundle(language)
        assert all(bundle[key] and bundle[key] != key for key in keys)
