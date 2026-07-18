import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email
        session["csrf_token"] = "token-1"


def make_user(email="alice@example.com", name="Alice"):
    return User(name, 28, email, "hashed", "Germany", "", "Engineer", "", [], [], [], [])


def test_ai_core_redirects_guest_to_home(monkeypatch):
    monkeypatch.setattr(app, "users", [make_user()])

    client = app.app.test_client()
    response = client.get("/ai_copilot")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_ai_core_page_renders_for_logged_user(monkeypatch):
    alice = make_user()

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_openai_status", lambda: {"enabled": False, "model": "test-model"})
    monkeypatch.setattr(app, "render_ai_core_history", lambda email, limit=12: "<aside>История</aside>")
    monkeypatch.setattr(app, "render_selected_ai_core_history", lambda email, history_index: "")

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/ai_copilot")

    assert response.status_code == 200
    assert "AI Core".encode("utf-8") in response.data
    assert "AI Core в резервном режиме".encode("utf-8") in response.data
    assert "<aside>История</aside>".encode("utf-8") in response.data


def test_ai_core_redirects_foreign_email_to_logged_user(monkeypatch):
    alice = make_user()

    monkeypatch.setattr(app, "users", [alice])

    client = app.app.test_client()
    login(client, "alice@example.com")

    response = client.get("/ai_copilot/bob@example.com")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/ai_copilot/alice@example.com")


def test_ai_core_post_generates_answer_and_records_memory(monkeypatch):
    alice = make_user()
    recorded = []

    monkeypatch.setattr(app, "users", [alice])
    monkeypatch.setattr(app, "get_openai_status", lambda: {"enabled": True, "model": "test-model"})
    monkeypatch.setattr(app, "generate_ai_copilot_answer", lambda user, question, mode="general": f"Answer for {question}")
    monkeypatch.setattr(app, "record_ai_core_memory", lambda email, mode, question, answer: recorded.append((email, mode, question, answer)))
    monkeypatch.setattr(app, "render_ai_core_history", lambda email, limit=12: "")

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
