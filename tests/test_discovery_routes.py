import app
from backend.models import User


def make_user(email, name="Alice", profession="Founder", interests=None):
    return User(
        name,
        28,
        email,
        "hashed",
        "Germany",
        "Building useful products",
        profession,
        "Partners",
        ["English"],
        ["Build"],
        interests or ["AI"],
        ["Sales"],
    )


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def test_matches_page_renders_visible_match(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob", "Designer", ["Design"])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [{"user": bob, "score": 87}])
    monkeypatch.setattr(app, "explain_match", lambda current_user, matched_user: ["Shared product goals"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "can_show_user_in_ai_recommendations", lambda viewer_email, candidate_user: True)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/matches/alice@example.com")

    assert response.status_code == 200
    assert b"Bob" in response.data
    assert b"87%" in response.data
    assert b"Shared product goals" in response.data


def test_matches_page_uses_saved_turkish_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "tr"
    bob = make_user("bob@example.com", "Bob", "Designer", ["Design"])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [{"user": bob, "score": 87}])
    monkeypatch.setattr(app, "explain_match", lambda current_user, matched_user: ["Shared product goals"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "can_show_user_in_ai_recommendations", lambda viewer_email, candidate_user: True)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/matches/alice@example.com", headers={"Accept-Language": "ru-RU"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "AI bu kişiyi neden öneriyor".encode("utf-8") in response.data
    assert "Profili aç".encode("utf-8") in response.data
    assert "Yaz".encode("utf-8") in response.data
    assert "Назад".encode("utf-8") not in response.data
    assert "Почему AI рекомендует".encode("utf-8") not in response.data
    assert "Открыть профиль".encode("utf-8") not in response.data


def test_search_page_posts_with_csrf_and_renders_results(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob", "AI Architect", ["AI"])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "is_account_deactivated", lambda user: False)
    monkeypatch.setattr(app, "get_user_privacy", lambda email: {"show_in_search": True, "vip_mode": False})

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/search/alice@example.com",
        data={"csrf_token": "token-1", "keyword": "architect"},
    )

    assert response.status_code == 200
    assert b"Bob" in response.data
    assert b"AI Architect" in response.data


def test_search_page_uses_saved_turkish_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "tr"

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)
    monkeypatch.setattr(app, "is_account_deactivated", lambda user: False)
    monkeypatch.setattr(app, "get_user_privacy", lambda email: {"show_in_search": True, "vip_mode": False})

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/search/alice@example.com",
        data={"csrf_token": "token-1", "keyword": "missing"},
        headers={"Accept-Language": "ru-RU"},
    )

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    assert "İnsan bul".encode("utf-8") in response.data
    assert "Sonuç bulunamadı.".encode("utf-8") in response.data
    assert "Поиск людей".encode("utf-8") not in response.data
    assert "Ничего не найдено".encode("utf-8") not in response.data


def test_radar_page_renders_recommended_people(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob", "AI Architect", ["AI"])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [{"user": bob, "score": 91}])
    monkeypatch.setattr(app, "can_show_user_in_ai_recommendations", lambda viewer_email, candidate_user: True)
    monkeypatch.setattr(app, "explain_user_match", lambda current_user, matched_user: ["Strong AI overlap"])
    monkeypatch.setattr(app, "explain_match", lambda current_user, matched_user: ["Fallback reason"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")

    client = app.app.test_client()

    response = client.get("/radar/alice@example.com")

    assert response.status_code == 200
    assert b"AI Life Radar" in response.data
    assert b"Bob" in response.data
    assert b"91%" in response.data
    assert b"Strong AI overlap" in response.data


def test_radar_page_respects_disabled_setting(monkeypatch):
    alice = make_user("alice@example.com", "Alice")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"ai_life_radar": False, "ai_recommendations": True})
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [])

    client = app.app.test_client()

    response = client.get("/radar/alice@example.com")

    assert response.status_code == 200
    assert "AI Life Radar выключен".encode("utf-8") in response.data
