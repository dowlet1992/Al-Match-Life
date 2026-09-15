import app
from html import unescape
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
    assert f"/profile/{bob.id}".encode() in response.data
    assert b"/profile/bob@example.com" not in response.data
    assert f"/chat/{alice.id}/{bob.id}".encode() in response.data


def test_discovery_accepts_uuid_and_rejects_another_users_uuid(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [])
    monkeypatch.setattr(app, "log_security_event", lambda *args: None)
    client = app.app.test_client()
    login(client, alice.email)

    assert client.get(f"/matches/{alice.id}").status_code == 200
    assert client.get(f"/search/{alice.id}").status_code == 200
    assert client.get(f"/radar/{alice.id}").status_code == 200
    assert client.get(f"/matches/{bob.id}").status_code == 403
    assert client.get(f"/search/{bob.id}").status_code == 403
    assert client.get(f"/radar/{bob.id}").status_code == 403


def test_matches_page_uses_saved_german_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "de"
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
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["settings"].encode() in response.data
    assert "Назад".encode("utf-8") not in response.data
    assert "Почему AI рекомендует".encode("utf-8") not in response.data
    assert "Открыть профиль".encode("utf-8") not in response.data


def test_turkish_matches_localize_level_and_deterministic_reasons(monkeypatch):
    alice = make_user("alice@example.com", "Alice", interests=["AI"])
    alice.language = "tr"
    bob = make_user("bob@example.com", "Bob", "Designer", ["AI"])
    match = {
        "user": bob,
        "score": 87,
        "signals": {"shared_interests": 18},
        "signal_details": {"shared_interests": ["ai"]},
    }
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [match])
    monkeypatch.setattr(app, "explain_match", lambda *args: (_ for _ in ()).throw(AssertionError("localized signals should be used")))
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    monkeypatch.setattr(app, "can_show_user_in_ai_recommendations", lambda viewer_email, candidate_user: True)

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(f"/matches/{alice.id}")
    visible_page = unescape(response.get_data(as_text=True))

    assert response.status_code == 200
    assert "Çok güçlü eşleşme" in visible_page
    assert "Ortak ilgi alanları: ai" in visible_page
    assert "Medium Match" not in visible_page
    assert "Общие интересы" not in visible_page


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
    assert f"/profile/{bob.id}".encode() in response.data
    assert b"/profile/bob@example.com" not in response.data


def test_search_page_uses_saved_german_language_without_russian_mixing(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "de"

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
    assert b'<html lang="de" dir="ltr">' in response.data
    assert app.translation_bundle("de")["settings"].encode() in response.data
    assert "Поиск людей".encode("utf-8") not in response.data
    assert "Ничего не найдено".encode("utf-8") not in response.data


def test_radar_page_renders_recommended_people(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    bob = make_user("bob@example.com", "Bob", "AI Architect", ["AI"])

    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [{"user": bob, "score": 91}])
    monkeypatch.setattr(app, "can_show_user_in_ai_recommendations", lambda viewer_email, candidate_user: True)
    monkeypatch.setattr(app, "explain_user_match", lambda *args: (_ for _ in ()).throw(AssertionError("Radar must not call a language model")))
    monkeypatch.setattr(app, "explain_match", lambda current_user, matched_user: ["Fallback reason"])
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")

    client = app.app.test_client()
    login(client, alice.email)

    response = client.get("/radar/alice@example.com")

    assert response.status_code == 200
    assert b"NOVIX Radar" in response.data
    assert b"Bob" in response.data
    assert b"91%" in response.data
    assert b"Fallback reason" in response.data
    assert f"/profile/{bob.id}".encode() in response.data
    assert b"/profile/bob@example.com" not in response.data


def test_radar_page_is_consistently_turkish(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "tr"
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"ai_life_radar": True, "ai_recommendations": True})
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [])

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(f"/radar/{alice.id}", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    visible_page = unescape(response.get_data(as_text=True))
    for copy in ("AI'ın şimdi önerdiği adımlar", "Bugün incelemeye değer kişiler", "Profilinizi güçlendirin", "AI Radar henüz uygun bir kişi bulamadı"):
        assert copy in visible_page
    for english_copy in ("Recommended next steps", "People worth viewing today", "Open profile", "found no suitable people yet"):
        assert english_copy not in visible_page


def test_turkish_radar_disabled_state_is_localized(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    alice.language = "tr"
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"ai_life_radar": False, "ai_recommendations": True})
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [])

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get(f"/radar/{alice.id}")

    assert response.status_code == 200
    visible_page = unescape(response.get_data(as_text=True))
    assert "NOVIX Radar kapalı" in visible_page
    assert "Öneri almak için ayarlardan NOVIX Radar'ı etkinleştirin." in visible_page


def test_radar_page_requires_authentication(monkeypatch):
    alice = make_user("alice@example.com", "Alice")
    monkeypatch.setattr(app, "users", [alice])

    response = app.app.test_client().get("/radar/alice@example.com")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_radar_page_respects_disabled_setting(monkeypatch):
    alice = make_user("alice@example.com", "Alice")

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"ai_life_radar": False, "ai_recommendations": True})
    monkeypatch.setattr(app, "find_best_matches", lambda current_user, users: [])

    client = app.app.test_client()
    login(client, alice.email)

    response = client.get("/radar/alice@example.com")

    assert response.status_code == 200
    assert "NOVIX Radar выключен".encode("utf-8") in response.data
