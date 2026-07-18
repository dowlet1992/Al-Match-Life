import app
from backend.models import User


def test_admin_moderation_page_rejects_non_admin(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/admin/moderation/alice@example.com")

    assert response.status_code == 403
    assert "Доступ закрыт".encode("utf-8") in response.data


def test_admin_moderation_page_lists_reports(monkeypatch):
    admin = User("Admin", 30, "admin@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    reports_data = {"reports": [{
        "id": "report-1",
        "reporter_email": "alice@example.com",
        "target_email": "bob@example.com",
        "reason": "spam",
        "details": "Bad content",
        "status": "new",
        "created_at": "2026-01-01 10:00:00",
    }]}
    monkeypatch.setattr(app, "users", [admin])
    monkeypatch.setattr(app, "load_reports", lambda: reports_data)
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "admin@example.com"

    response = client.get("/admin/moderation/admin@example.com")

    assert response.status_code == 200
    assert b"Moderation" in response.data
    assert b"report-1" in response.data
    assert b"alice@example.com" in response.data
    assert b"bob@example.com" in response.data


def test_admin_moderation_page_updates_report(monkeypatch):
    admin = User("Admin", 30, "admin@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    reports_data = {"reports": [{"id": "report-1", "status": "new", "created_at": "2026-01-01 10:00:00"}]}
    saved = []
    monkeypatch.setattr(app, "users", [admin])
    monkeypatch.setattr(app, "load_reports", lambda: reports_data)
    monkeypatch.setattr(app, "save_reports", lambda data: saved.append(data))
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "admin@example.com"
        session["csrf_token"] = "token-1"

    response = client.post(
        "/admin/moderation/admin@example.com",
        data={
            "csrf_token": "token-1",
            "report_id": "report-1",
            "status": "resolved",
            "note": "Handled",
            "action": "warning_sent",
        },
    )

    assert response.status_code == 302
    assert saved
    assert saved[0]["reports"][0]["status"] == "resolved"
    assert saved[0]["reports"][0]["reviewed_by"] == "admin@example.com"
    assert saved[0]["reports"][0]["moderation_note"] == "Handled"
