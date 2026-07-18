import app


def test_i18n_api_detects_browser_or_device_language():
    client = app.app.test_client()

    response = client.get("/api/i18n", headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["locale"]["language"] == "de"
    assert data["locale"]["requested_language"] == "de"
    assert data["locale"]["supported"] is True
    assert data["locale"]["direction"] == "ltr"
    assert data["translations"]["settings"] == "Einstellungen"


def test_i18n_api_allows_explicit_mobile_language_override():
    client = app.app.test_client()

    response = client.get("/api/i18n?lang=tr", headers={"Accept-Language": "de-DE"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"]["language"] == "tr"
    assert data["locale"]["requested_language"] == "tr"
    assert data["translations"]["settings"] == "Ayarlar"


def test_i18n_api_uses_saved_session_language_preference():
    client = app.app.test_client()

    save_response = client.post("/api/i18n/language", json={"language": "fr-FR"})

    assert save_response.status_code == 200
    save_data = save_response.get_json()
    assert save_data["ok"] is True
    assert save_data["saved"] is True
    assert save_data["locale"]["language"] == "fr"
    assert save_data["translations"]["settings"] == "Paramètres"

    response = client.get("/api/i18n", headers={"Accept-Language": "en-US,en;q=0.9"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"]["language"] == "fr"
    assert data["translations"]["settings"] == "Paramètres"


def test_i18n_api_query_language_overrides_saved_session_language():
    client = app.app.test_client()
    client.post("/api/i18n/language", json={"language": "fr"})

    response = client.get("/api/i18n?lang=it", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"]["language"] == "it"
    assert data["translations"]["settings"] == "Impostazioni"


def test_i18n_api_rejects_planned_language_as_saved_ui_preference():
    client = app.app.test_client()

    response = client.post("/api/i18n/language", json={"language": "sv-SE"})

    assert response.status_code == 400
    data = response.get_json()
    assert data["ok"] is False
    assert data["error"] == "language_not_supported"
    assert data["locale"]["requested_language"] == "sv"
    assert data["locale"]["translation_status"] == "planned"
    assert data["locale"]["translation_completion_percent"] == 0


def test_i18n_api_supports_arabic_rtl_language():
    client = app.app.test_client()

    response = client.get("/api/i18n", headers={"Accept-Language": "ar-SA,ar;q=0.9"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"]["language"] == "ar"
    assert data["locale"]["requested_language"] == "ar"
    assert data["locale"]["supported"] is True
    assert data["locale"]["fallback_language"] == ""
    assert data["locale"]["direction"] == "rtl"
    assert data["locale"]["requested_direction"] == "rtl"
    assert data["translations"]["settings"] == "الإعدادات"


def test_i18n_api_uses_secondary_supported_device_language():
    client = app.app.test_client()

    response = client.get("/api/i18n", headers={"Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"]["language"] == "en"
    assert data["locale"]["requested_language"] == "sv"
    assert data["locale"]["supported"] is False
    assert data["locale"]["fallback_language"] == "en"
    assert data["locale"]["translation_status"] == "planned"
    assert data["locale"]["translation_completion_percent"] == 0
    assert data["locale"]["requested_language_name"] == "Svenska"
    assert data["translations"]["settings"] == "Settings"


def test_i18n_api_returns_supported_language_catalog():
    client = app.app.test_client()

    response = client.get("/api/i18n")

    assert response.status_code == 200
    languages = response.get_json()["locale"]["supported_languages"]
    assert {
        "code": "ru",
        "name": "Русский",
        "direction": "ltr",
        "translation_status": "supported",
        "completion_percent": 100,
    } in languages
    assert {
        "code": "en",
        "name": "English",
        "direction": "ltr",
        "translation_status": "supported",
        "completion_percent": 100,
    } in languages
    assert {
        "code": "ar",
        "name": "العربية",
        "direction": "rtl",
        "translation_status": "supported",
        "completion_percent": 100,
    } in languages


def test_i18n_api_returns_global_language_catalog_for_mobile():
    client = app.app.test_client()

    response = client.get("/api/i18n", headers={"Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8"})

    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"]["requested_language"] == "sv"
    assert data["locale"]["requested_language_name"] == "Svenska"
    assert data["locale"]["translation_status"] == "planned"
    assert data["locale"]["translation_completion_percent"] == 0
    assert {
        "code": "sv",
        "name": "Svenska",
        "direction": "ltr",
        "translation_status": "planned",
        "completion_percent": 0,
    } in data["locale"]["language_catalog"]
    assert {
        "code": "ar",
        "name": "العربية",
        "direction": "rtl",
        "translation_status": "supported",
        "completion_percent": 100,
    } in data["locale"]["language_catalog"]


def test_i18n_api_supports_spanish_and_french_startup_languages():
    client = app.app.test_client()

    spanish = client.get("/api/i18n", headers={"Accept-Language": "es-ES,es;q=0.9"})
    french = client.get("/api/i18n", headers={"Accept-Language": "fr-FR,fr;q=0.9"})

    assert spanish.status_code == 200
    assert spanish.get_json()["locale"]["language"] == "es"
    assert spanish.get_json()["locale"]["translation_status"] == "supported"
    assert spanish.get_json()["translations"]["settings"] == "Ajustes"
    assert french.status_code == 200
    assert french.get_json()["locale"]["language"] == "fr"
    assert french.get_json()["locale"]["translation_status"] == "supported"
    assert french.get_json()["translations"]["settings"] == "Paramètres"


def test_i18n_api_supports_portuguese_and_italian_startup_languages():
    client = app.app.test_client()

    portuguese = client.get("/api/i18n", headers={"Accept-Language": "pt-BR,pt;q=0.9"})
    italian = client.get("/api/i18n", headers={"Accept-Language": "it-IT,it;q=0.9"})

    assert portuguese.status_code == 200
    assert portuguese.get_json()["locale"]["language"] == "pt"
    assert portuguese.get_json()["locale"]["translation_status"] == "supported"
    assert portuguese.get_json()["translations"]["settings"] == "Definições"
    assert italian.status_code == 200
    assert italian.get_json()["locale"]["language"] == "it"
    assert italian.get_json()["locale"]["translation_status"] == "supported"
    assert italian.get_json()["translations"]["settings"] == "Impostazioni"


def test_i18n_api_supports_hindi_and_indonesian_startup_languages():
    client = app.app.test_client()

    hindi = client.get("/api/i18n", headers={"Accept-Language": "hi-IN,hi;q=0.9"})
    indonesian = client.get("/api/i18n", headers={"Accept-Language": "id-ID,id;q=0.9"})

    assert hindi.status_code == 200
    assert hindi.get_json()["locale"]["language"] == "hi"
    assert hindi.get_json()["locale"]["translation_status"] == "supported"
    assert hindi.get_json()["translations"]["settings"] == "सेटिंग्स"
    assert indonesian.status_code == 200
    assert indonesian.get_json()["locale"]["language"] == "id"
    assert indonesian.get_json()["locale"]["translation_status"] == "supported"
    assert indonesian.get_json()["translations"]["settings"] == "Pengaturan"


def test_i18n_api_supports_chinese_and_japanese_startup_languages():
    client = app.app.test_client()

    chinese = client.get("/api/i18n", headers={"Accept-Language": "zh-CN,zh;q=0.9"})
    japanese = client.get("/api/i18n", headers={"Accept-Language": "ja-JP,ja;q=0.9"})

    assert chinese.status_code == 200
    assert chinese.get_json()["locale"]["language"] == "zh"
    assert chinese.get_json()["locale"]["translation_status"] == "supported"
    assert chinese.get_json()["translations"]["settings"] == "设置"
    assert japanese.status_code == 200
    assert japanese.get_json()["locale"]["language"] == "ja"
    assert japanese.get_json()["locale"]["translation_status"] == "supported"
    assert japanese.get_json()["translations"]["settings"] == "設定"


def test_i18n_api_supports_korean_startup_language():
    client = app.app.test_client()

    korean = client.get("/api/i18n", headers={"Accept-Language": "ko-KR,ko;q=0.9"})

    assert korean.status_code == 200
    assert korean.get_json()["locale"]["language"] == "ko"
    assert korean.get_json()["locale"]["translation_status"] == "supported"
    assert korean.get_json()["translations"]["settings"] == "설정"


def test_i18n_api_supports_polish_and_dutch_startup_languages():
    client = app.app.test_client()

    polish = client.get("/api/i18n", headers={"Accept-Language": "pl-PL,pl;q=0.9"})
    dutch = client.get("/api/i18n", headers={"Accept-Language": "nl-NL,nl;q=0.9"})

    assert polish.status_code == 200
    assert polish.get_json()["locale"]["language"] == "pl"
    assert polish.get_json()["locale"]["translation_status"] == "supported"
    assert polish.get_json()["translations"]["settings"] == "Ustawienia"
    assert dutch.status_code == 200
    assert dutch.get_json()["locale"]["language"] == "nl"
    assert dutch.get_json()["locale"]["translation_status"] == "supported"
    assert dutch.get_json()["translations"]["settings"] == "Instellingen"


def test_i18n_api_supports_ukrainian_and_romanian_startup_languages():
    client = app.app.test_client()

    ukrainian = client.get("/api/i18n", headers={"Accept-Language": "uk-UA,uk;q=0.9"})
    romanian = client.get("/api/i18n", headers={"Accept-Language": "ro-RO,ro;q=0.9"})

    assert ukrainian.status_code == 200
    assert ukrainian.get_json()["locale"]["language"] == "uk"
    assert ukrainian.get_json()["locale"]["translation_status"] == "supported"
    assert ukrainian.get_json()["translations"]["settings"] == "Налаштування"
    assert romanian.status_code == 200
    assert romanian.get_json()["locale"]["language"] == "ro"
    assert romanian.get_json()["locale"]["translation_status"] == "supported"
    assert romanian.get_json()["translations"]["settings"] == "Setări"
