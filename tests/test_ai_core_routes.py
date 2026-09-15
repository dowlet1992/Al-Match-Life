import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email="alice@example.com", name="Alice", language=""):
    user = User(name, 28, email, "hashed", "Germany", "", "Engineer", "", [], [], [], [])
    user.language = language
    return user


def test_ai_core_redirects_guest_to_home(monkeypatch):
    monkeypatch.setattr(app, "users", [make_user()])

    client = app.app.test_client()
    response = client.get("/ai_copilot")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_ai_core_page_renders_for_logged_user(monkeypatch):
    alice = make_user()

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": False, "model": "test-model"})
    monkeypatch.setattr(app, "render_ai_core_history", lambda email, limit=12: [{
        "index": 0, "mode_title": "AI Core", "question": "История", "time": "10:00",
    }])
    monkeypatch.setattr(app, "render_selected_ai_core_history", lambda email, history_index: None)

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/ai_copilot")

    assert response.status_code == 200
    assert "AI Assistant".encode("utf-8") in response.data
    assert "AI Assistant временно недоступен".encode("utf-8") in response.data
    assert "История".encode("utf-8") in response.data
    assert b"/static/ai-core.js" in response.data
    assert b"data-ai-core-form" in response.data


def test_ai_core_page_is_consistently_turkish(monkeypatch):
    alice = make_user(language="tr")
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": False, "model": "test-model"})
    monkeypatch.setattr(app, "render_ai_core_history", lambda email, limit=12: [])
    monkeypatch.setattr(app, "render_selected_ai_core_history", lambda email, history_index: None)

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get("/ai_copilot", headers={"Accept-Language": "en-US"})

    assert response.status_code == 200
    assert b'<html lang="tr" dir="ltr">' in response.data
    for copy in (
        "AI Asistan", "Geçmiş", "Henüz önceki bir konuşma yok.", "Asistan modu",
        "Bir soru sorun", "Gönder", "Asistan geçici olarak kullanılamıyor.",
    ):
        assert copy.encode() in response.data
    for english_copy in ("History", "Ask a question", "No previous conversations yet."):
        assert english_copy.encode() not in response.data


def test_ai_core_redirects_foreign_email_to_logged_user(monkeypatch):
    alice = make_user()

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/ai_copilot/bob@example.com")

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/ai_copilot/{alice.id}")


def test_ai_core_post_generates_answer_and_records_memory(monkeypatch):
    alice = make_user()
    recorded = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": True, "model": "test-model"})
    monkeypatch.setattr(app, "generate_ai_copilot_answer", lambda user, question, mode="general": f"Answer for {question}")
    monkeypatch.setattr(app, "record_ai_core_memory", lambda email, mode, question, answer: recorded.append((email, mode, question, answer)))
    monkeypatch.setattr(app, "render_ai_core_history", lambda email, limit=12: [])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/ai_copilot/alice@example.com",
        data={
            "csrf_token": "token-1",
            "question": "How to improve my profile?",
        },
    )

    assert response.status_code == 200
    assert "Answer for How to improve my profile?".encode("utf-8") in response.data
    assert recorded == [(
        "alice@example.com",
        "general",
        "How to improve my profile?",
        "Answer for How to improve my profile?",
    )]


def test_ai_core_json_post_uses_selected_mode_without_page_reload(monkeypatch):
    alice = make_user()
    recorded = []
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "generate_ai_copilot_answer", lambda user, question, mode="general": f"{mode}: {question}")
    monkeypatch.setattr(app, "record_ai_core_memory", lambda *items: recorded.append(items))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/ai_copilot/{alice.id}",
        headers={"X-CSRF-Token": "token-1"},
        json={"question": "Improve positioning", "mode": "profile"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.get_json()["answer"] == "profile: Improve positioning"
    assert recorded[0][1] == "profile"


def test_ai_core_rate_limits_expensive_generation(monkeypatch):
    alice = make_user()
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app.ai_assistant_limiter, "allow", lambda key: False)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/ai_copilot/{alice.id}",
        headers={"X-CSRF-Token": "token-1"},
        json={"question": "Generate repeatedly", "mode": "general"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.get_json()["error"] == "assistant_rate_limited"


def test_ai_core_post_rejects_missing_csrf(monkeypatch):
    alice = make_user()

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.post(
        "/ai_copilot/alice@example.com",
        data={"question": "No csrf"},
    )

    assert response.status_code == 403


def test_ai_core_history_escapes_saved_content(monkeypatch):
    alice = make_user()
    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": False, "model": "test-model"})
    monkeypatch.setattr(app, "render_ai_core_history", lambda email, limit=12: [])
    monkeypatch.setattr(app, "render_selected_ai_core_history", lambda email, history_index: {
        "time": "10:00",
        "mode_title": "AI Core",
        "question": '<img src=x onerror="alert(1)">',
        "answer": '<script>alert(2)</script>',
    })

    client = app.app.test_client()
    login(client, alice.email)
    response = client.get("/ai_copilot/alice@example.com?history=0")

    assert response.status_code == 200
    assert b'<img src=x onerror="alert(1)">' not in response.data
    assert b"<script>alert(2)</script>" not in response.data
    assert b"&lt;script&gt;alert(2)&lt;/script&gt;" in response.data


def test_ai_core_helpers_return_data_instead_of_html():
    source = open("app.py", encoding="utf-8").read()
    history_source = source[
        source.index("def render_ai_core_history"):
        source.index("def get_ai_provider_status")
    ]

    assert "<aside" not in history_source
    assert "history_html" not in history_source
    assert "user_card" not in source


def test_ai_core_generation_can_be_cancelled_and_times_out_safely():
    template = open("frontend/ai_core.html", encoding="utf-8").read()
    script = open("static/ai-core.js", encoding="utf-8").read()

    assert "data-ai-stop" in template
    assert "data-cancelled-label" in template
    assert "data-timeout-label" in template
    assert "data-error-label" in template
    assert "new AbortController()" in script
    assert "signal: requestController.signal" in script
    assert "requestAbortReason = 'user'" in script
    assert "requestAbortReason = 'timeout'" in script
    assert "requestController.abort()" in script
    assert "}, 120000)" in script
    assert "error.name === 'AbortError'" in script
    assert "form.dataset.errorLabel" in script
    assert "error.message ||" not in script
