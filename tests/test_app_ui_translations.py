import app
from backend.i18n import LANGUAGE_CATALOG, SUPPORTED_LANGUAGES


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


def test_ai_discover_translations_use_supported_languages_without_russian_fallback():
    assert app.t("create_post", "es-ES") == "Crear publicación"
    assert app.t("create_post", "fr-FR") == "Créer une publication"
    assert app.t("create_post", "pt-BR") == "Criar publicação"
    assert app.t("create_post", "it-IT") == "Crea post"
    assert app.t("create_post", "hi-IN") == "पोस्ट बनाएँ"
    assert app.t("create_post", "id-ID") == "Buat postingan"
    assert app.t("create_post", "zh-CN") == "创建动态"
    assert app.t("create_post", "ja-JP") == "投稿を作成"
    assert app.t("create_post", "ko-KR") == "게시물 만들기"
    assert app.t("create_post", "pl-PL") == "Utwórz post"
    assert app.t("create_post", "nl-NL") == "Post maken"
    assert app.t("create_post", "uk-UA") == "Створити допис"
    assert app.t("create_post", "ro-RO") == "Creează postare"
    assert app.t("create_post", "ar-AE") == "إنشاء منشور"
