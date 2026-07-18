from backend.i18n import (
    build_locale_payload,
    detect_language,
    is_rtl_language,
    language_catalog_options,
    language_display_name,
    language_translation_status,
    normalize_language_code,
    normalize_requested_language_code,
    parse_accept_language_header,
    translate,
    translation_coverage_report,
    translation_completion_percent,
    translation_bundle,
)


def test_detect_language_uses_accept_language_primary_tag():
    assert detect_language("de-DE,de;q=0.9,en;q=0.8") == "de"
    assert detect_language("tr-TR") == "tr"
    assert detect_language("ar-AE,ar;q=0.9,en;q=0.8") == "ar"
    assert detect_language("es-ES,es;q=0.9,en;q=0.8") == "es"
    assert detect_language("fr-FR,fr;q=0.9,en;q=0.8") == "fr"
    assert detect_language("pt-BR,pt;q=0.9,en;q=0.8") == "pt"
    assert detect_language("it-IT,it;q=0.9,en;q=0.8") == "it"
    assert detect_language("hi-IN,hi;q=0.9,en;q=0.8") == "hi"
    assert detect_language("id-ID,id;q=0.9,en;q=0.8") == "id"
    assert detect_language("zh-CN,zh;q=0.9,en;q=0.8") == "zh"
    assert detect_language("ja-JP,ja;q=0.9,en;q=0.8") == "ja"
    assert detect_language("ko-KR,ko;q=0.9,en;q=0.8") == "ko"
    assert detect_language("pl-PL,pl;q=0.9,en;q=0.8") == "pl"
    assert detect_language("nl-NL,nl;q=0.9,en;q=0.8") == "nl"
    assert detect_language("uk-UA,uk;q=0.9,en;q=0.8") == "uk"
    assert detect_language("ro-RO,ro;q=0.9,en;q=0.8") == "ro"


def test_detect_language_falls_back_to_default_for_unsupported_language():
    assert detect_language("sv-SE") == "ru"


def test_detect_language_uses_next_supported_language_preference():
    assert detect_language("sv-SE,sv;q=0.9,en-US;q=0.8,de;q=0.7") == "en"


def test_parse_accept_language_header_respects_quality_priority():
    preferences = parse_accept_language_header("es-ES;q=0.5,de-DE;q=0.9,en-US;q=0.8")

    assert [item["code"] for item in preferences] == ["de-de", "en-us", "es-es"]


def test_translate_falls_back_to_default_key():
    assert translate("settings", "en") == "Settings"
    assert translate("settings", "unknown") == "Настройки"
    assert translate("missing_key", "en") == "missing_key"


def test_translation_bundle_contains_language_code():
    bundle = translation_bundle("en-US")

    assert bundle["language_code"] == "en"
    assert bundle["profile"] == "Profile"


def test_translation_bundle_supports_arabic():
    bundle = translation_bundle("ar-AE")

    assert bundle["language_code"] == "ar"
    assert bundle["text_direction"] == "rtl"
    assert bundle["settings"] == "الإعدادات"
    assert bundle["onboarding_title"] == "بداية سريعة"


def test_translation_bundle_supports_spanish_and_french():
    spanish = translation_bundle("es-ES")
    french = translation_bundle("fr-FR")

    assert spanish["language_code"] == "es"
    assert spanish["settings"] == "Ajustes"
    assert spanish["onboarding_title"] == "Inicio rápido"
    assert french["language_code"] == "fr"
    assert french["settings"] == "Paramètres"
    assert french["onboarding_title"] == "Démarrage rapide"


def test_translation_bundle_supports_portuguese_and_italian():
    portuguese = translation_bundle("pt-BR")
    italian = translation_bundle("it-IT")

    assert portuguese["language_code"] == "pt"
    assert portuguese["settings"] == "Definições"
    assert portuguese["onboarding_title"] == "Início rápido"
    assert italian["language_code"] == "it"
    assert italian["settings"] == "Impostazioni"
    assert italian["onboarding_title"] == "Avvio rapido"


def test_translation_bundle_supports_hindi_and_indonesian():
    hindi = translation_bundle("hi-IN")
    indonesian = translation_bundle("id-ID")

    assert hindi["language_code"] == "hi"
    assert hindi["settings"] == "सेटिंग्स"
    assert hindi["onboarding_title"] == "त्वरित शुरुआत"
    assert indonesian["language_code"] == "id"
    assert indonesian["settings"] == "Pengaturan"
    assert indonesian["onboarding_title"] == "Mulai cepat"


def test_translation_bundle_supports_chinese_and_japanese():
    chinese = translation_bundle("zh-CN")
    japanese = translation_bundle("ja-JP")

    assert chinese["language_code"] == "zh"
    assert chinese["settings"] == "设置"
    assert chinese["onboarding_title"] == "快速开始"
    assert japanese["language_code"] == "ja"
    assert japanese["settings"] == "設定"
    assert japanese["onboarding_title"] == "クイックスタート"


def test_translation_bundle_supports_korean():
    korean = translation_bundle("ko-KR")

    assert korean["language_code"] == "ko"
    assert korean["settings"] == "설정"
    assert korean["onboarding_title"] == "빠른 시작"


def test_translation_bundle_supports_polish_and_dutch():
    polish = translation_bundle("pl-PL")
    dutch = translation_bundle("nl-NL")

    assert polish["language_code"] == "pl"
    assert polish["settings"] == "Ustawienia"
    assert polish["onboarding_title"] == "Szybki start"
    assert dutch["language_code"] == "nl"
    assert dutch["settings"] == "Instellingen"
    assert dutch["onboarding_title"] == "Snelle start"


def test_translation_bundle_supports_ukrainian_and_romanian():
    ukrainian = translation_bundle("uk-UA")
    romanian = translation_bundle("ro-RO")

    assert ukrainian["language_code"] == "uk"
    assert ukrainian["settings"] == "Налаштування"
    assert ukrainian["onboarding_title"] == "Швидкий старт"
    assert romanian["language_code"] == "ro"
    assert romanian["settings"] == "Setări"
    assert romanian["onboarding_title"] == "Start rapid"


def test_all_supported_languages_have_complete_startup_translations():
    report = translation_coverage_report()

    assert report
    assert all(item["complete"] for item in report.values())
    assert all(item["missing_keys"] == [] for item in report.values())
    assert all(item["completion_percent"] == 100 for item in report.values())


def test_translation_completion_percent_marks_supported_and_planned_languages():
    assert translation_completion_percent("en-US") == 100
    assert translation_completion_percent("ar-AE") == 100
    assert translation_completion_percent("sv-SE") == 0


def test_normalize_language_code_supports_session_values():
    assert normalize_language_code("de") == "de"
    assert normalize_language_code("de-DE") == "de"


def test_normalize_requested_language_code_keeps_unsupported_device_language():
    assert normalize_requested_language_code("es-ES,es;q=0.9") == "es"


def test_language_catalog_tracks_planned_and_supported_languages():
    assert language_display_name("fr-FR") == "Français"
    assert language_display_name("hi-IN") == "हिन्दी"
    assert language_translation_status("ar-AE") == "supported"
    assert language_translation_status("fr-FR") == "supported"
    assert language_translation_status("es-ES") == "supported"
    assert language_translation_status("pt-BR") == "supported"
    assert language_translation_status("it-IT") == "supported"
    assert language_translation_status("hi-IN") == "supported"
    assert language_translation_status("id-ID") == "supported"
    assert language_translation_status("zh-CN") == "supported"
    assert language_translation_status("ja-JP") == "supported"
    assert language_translation_status("ko-KR") == "supported"
    assert language_translation_status("pl-PL") == "supported"
    assert language_translation_status("nl-NL") == "supported"
    assert language_translation_status("uk-UA") == "supported"
    assert language_translation_status("ro-RO") == "supported"
    assert language_translation_status("sv-SE") == "planned"
    assert language_translation_status("zz") == "unknown"


def test_language_catalog_contains_global_mobile_languages():
    catalog = language_catalog_options()

    assert {
        "code": "zh",
        "name": "中文",
        "direction": "ltr",
        "translation_status": "supported",
        "completion_percent": 100,
    } in catalog
    assert {
        "code": "ur",
        "name": "اردو",
        "direction": "rtl",
        "translation_status": "planned",
        "completion_percent": 0,
    } in catalog
    assert {
        "code": "ar",
        "name": "العربية",
        "direction": "rtl",
        "translation_status": "supported",
        "completion_percent": 100,
    } in catalog


def test_build_locale_payload_reports_supported_language():
    payload = build_locale_payload(accept_language_header="de-DE,de;q=0.9")

    assert payload["language"] == "de"
    assert payload["language_name"] == "Deutsch"
    assert payload["requested_language"] == "de"
    assert payload["requested_language_name"] == "Deutsch"
    assert payload["supported"] is True
    assert payload["translation_status"] == "supported"
    assert payload["translation_completion_percent"] == 100
    assert payload["fallback_language"] == ""
    assert payload["direction"] == "ltr"


def test_build_locale_payload_reports_fallback_for_unsupported_language():
    payload = build_locale_payload(accept_language_header="sv-SE,sv;q=0.9")

    assert payload["language"] == "ru"
    assert payload["requested_language"] == "sv"
    assert payload["requested_language_name"] == "Svenska"
    assert payload["supported"] is False
    assert payload["translation_status"] == "planned"
    assert payload["translation_completion_percent"] == 0
    assert payload["fallback_language"] == "ru"


def test_build_locale_payload_uses_supported_secondary_device_language():
    payload = build_locale_payload(accept_language_header="sv-SE,sv;q=0.9,en-US;q=0.8")

    assert payload["language"] == "en"
    assert payload["requested_language"] == "sv"
    assert payload["supported"] is False
    assert payload["fallback_language"] == "en"


def test_locale_payload_tracks_rtl_requested_direction():
    payload = build_locale_payload(accept_language_header="ar-SA,ar;q=0.9")

    assert payload["language"] == "ar"
    assert payload["requested_language"] == "ar"
    assert payload["supported"] is True
    assert payload["fallback_language"] == ""
    assert payload["direction"] == "rtl"
    assert payload["requested_direction"] == "rtl"
    assert is_rtl_language("ar-SA") is True
