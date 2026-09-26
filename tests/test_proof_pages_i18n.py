import app
from backend.i18n import UI_TRANSLATIONS, translation_bundle
from backend.models import User


def make_user(email, language="de"):
    user = User("Alice", 28, email, "hashed", "Germany", "", "Founder", "", [], [], [], [])
    user.language = language
    return user


def test_proof_profile_uses_viewer_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "de")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "load_proofs", lambda: {"proofs": [
        {"email": "alice@example.com", "type": "video"},
        {"email": "alice@example.com", "type": "photo"},
    ]})

    client = app.app.test_client()

    response = client.get("/proof/alice@example.com/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["back"].encode() in response.data
    assert "Видео-доказательства".encode("utf-8") not in response.data
    assert "Пользователь загрузил".encode("utf-8") not in response.data


def test_add_proof_page_uses_viewer_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "de")

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()

    response = client.get("/add_proof/alice@example.com/alice@example.com/video", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["back"].encode() in response.data
    assert "Добавить Proof".encode("utf-8") not in response.data
    assert "Название".encode("utf-8") not in response.data


def test_add_proof_rejects_unknown_type(monkeypatch):
    alice = make_user("alice@example.com", "en")
    monkeypatch.setattr(app, "users", [alice])

    response = app.app.test_client().get(
        "/add_proof/alice@example.com/alice@example.com/not-a-proof"
    )

    assert response.status_code == 404


def test_add_proof_post_requires_profile_owner(monkeypatch):
    alice = make_user("alice@example.com", "en")
    bob = make_user("bob@example.com", "en")
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = bob.email
        session_data["session_version"] = 1
        session_data["csrf_token"] = "proof-csrf"

    response = client.post(
        "/add_proof/bob@example.com/alice@example.com/video",
        data={
            "csrf_token": "proof-csrf",
            "title": "Not mine",
            "description": "Must not be stored",
        },
    )

    assert response.status_code == 403
def test_reviewed_arabic_profile_proof_privacy_and_social_copy_is_complete():
    keys = {
        "ai_level_minimal", "security_category_system", "trust_diamond_tooltip",
        "trust_gold_tooltip", "trust_silver_tooltip", "trust_bronze_tooltip",
        "proof_profile_intro", "proof_video_title", "proof_video_intro",
        "proof_photo_title", "proof_photo_intro", "proof_documents_title",
        "proof_documents_intro", "proof_projects_title", "proof_projects_intro",
        "proof_achievements_title", "proof_achievements_intro", "trust_proof_intro",
        "proof_summary", "add_proof_title", "title_label", "description_label",
        "save", "privacy_ai_control", "privacy_ai_intro", "receive_recommendations",
        "receive_recommendations_help", "allow_messages", "allow_messages_help",
        "verified_only_help", "vip_private_mode", "vip_private_mode_help",
        "messages_closed", "block", "restrict", "show_stories",
        "hide_my_stories", "more", "copy_link", "link_copied", "share_profile",
        "qr_code", "report",
    }
    assert translation_bundle("ar")["text_direction"] == "rtl"
    assert {
        key for key in keys
        if UI_TRANSLATIONS["ar"][key] == UI_TRANSLATIONS["en"][key]
    } == set()
