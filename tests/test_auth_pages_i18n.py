import app


def test_home_page_uses_accept_language_for_login_screen():
    client = app.app.test_client()

    response = client.get("/", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="en" dir="ltr">' in response.data
    assert b"Find the right people" in response.data
    assert b"Forgot password?" in response.data
    assert b"Create account" in response.data


def test_register_page_uses_accept_language_for_registration_screen():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "de-DE"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert b"Konto erstellen" in response.data
    assert b"Basisdaten" in response.data
    assert b"Passwort" in response.data


def test_register_page_uses_saved_language_preference_over_device_language():
    client = app.app.test_client()
    save_response = client.post("/api/i18n/language", json={"language": "fr"})

    assert save_response.status_code == 200

    response = client.get("/register", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="fr" dir="ltr">' in response.data
    assert "Créer un compte".encode("utf-8") in response.data


def test_register_page_falls_back_to_russian_for_unsupported_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "sv-SE"})

    assert response.status_code == 200
    assert b'<html lang="ru" dir="ltr">' in response.data
    assert "Создайте аккаунт".encode("utf-8") in response.data


def test_register_page_supports_arabic_rtl_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "ar-AE,ar;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="ar" dir="rtl">' in response.data
    assert "إنشاء حساب".encode("utf-8") in response.data


def test_register_page_supports_spanish_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "es-ES,es;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="es" dir="ltr">' in response.data
    assert "Crear cuenta".encode("utf-8") in response.data
    assert "Datos básicos".encode("utf-8") in response.data


def test_register_page_supports_portuguese_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "pt-BR,pt;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="pt" dir="ltr">' in response.data
    assert "Criar conta".encode("utf-8") in response.data
    assert "Dados básicos".encode("utf-8") in response.data


def test_register_page_supports_hindi_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "hi-IN,hi;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="hi" dir="ltr">' in response.data
    assert "खाता बनाएँ".encode("utf-8") in response.data
    assert "बुनियादी जानकारी".encode("utf-8") in response.data


def test_register_page_supports_chinese_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "zh-CN,zh;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="zh" dir="ltr">' in response.data
    assert "创建账户".encode("utf-8") in response.data
    assert "基础信息".encode("utf-8") in response.data


def test_register_page_supports_korean_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "ko-KR,ko;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="ko" dir="ltr">' in response.data
    assert "계정 만들기".encode("utf-8") in response.data
    assert "기본 정보".encode("utf-8") in response.data


def test_register_page_supports_polish_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "pl-PL,pl;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="pl" dir="ltr">' in response.data
    assert "Utwórz konto".encode("utf-8") in response.data
    assert "Dane podstawowe".encode("utf-8") in response.data


def test_register_page_supports_ukrainian_language():
    client = app.app.test_client()

    response = client.get("/register", headers={"Accept-Language": "uk-UA,uk;q=0.9"})

    assert response.status_code == 200
    assert b'<html lang="uk" dir="ltr">' in response.data
    assert "Створити акаунт".encode("utf-8") in response.data
    assert "Основні дані".encode("utf-8") in response.data
