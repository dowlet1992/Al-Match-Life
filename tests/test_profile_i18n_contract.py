from pathlib import Path

from backend.i18n import missing_translation_keys, translation_bundle


def test_profile_vocabulary_is_complete_in_maintained_languages():
    required = {
        "profile_back", "friends", "message", "already_friends", "request_sent",
        "add_friend", "unfollow", "follow", "profile_insight", "information",
        "age_label", "country_label", "looking_for_label", "about_label",
        "languages_label", "goals_label", "interests_label", "skills_label",
        "verification_label", "proof_description", "open_proof_profile", "avatar_alt",
    }
    for language in ("ru", "en", "de", "tr"):
        bundle = translation_bundle(language)
        assert required <= bundle.keys()
        assert not missing_translation_keys(language)


def test_profile_template_has_no_legacy_hardcoded_russian_labels():
    source = Path("frontend/profile.html").read_text(encoding="utf-8")
    for label in ("Назад", "Друзья", "Подписчики", "Сообщение", "Возраст", "Страна", "Навыки"):
        assert f">{label}<" not in source
