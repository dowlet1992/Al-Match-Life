import app
from backend.models import User


def test_admin_reports_requires_authentication():
    client = app.app.test_client()

    response = client.get("/api/admin/moderation/reports")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Authentication required"


def test_admin_reports_rejects_non_admin(monkeypatch):
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "alice@example.com"

    response = client.get("/api/admin/moderation/reports")

    assert response.status_code == 403
    assert response.get_json()["error"] == "Admin access required"


def test_admin_reports_lists_reports_for_admin(monkeypatch):
    admin = User("Admin", 30, "admin@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    reports_data = {"reports": [
        {
            "id": "report-1",
            "reporter_email": "alice@example.com",
            "target_email": "bob@example.com",
            "reason": "spam",
            "details": "Bad content",
            "status": "new",
            "created_at": "2026-01-01 10:00:00",
        },
        {
            "id": "report-2",
            "reporter_email": "carol@example.com",
            "target_email": "bob@example.com",
            "reason": "fake",
            "details": "",
            "status": "resolved",
            "created_at": "2026-01-02 10:00:00",
        },
    ]}
    monkeypatch.setattr(app, "users", [admin])
    monkeypatch.setattr(app, "load_reports", lambda: reports_data)
    monkeypatch.setattr(app, "log_security_event", lambda event_type, email="", details="": None)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "admin@example.com"

    response = client.get("/api/admin/moderation/reports?status=new&target_email=BOB@example.com")

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["summary"]["total"] == 2
    assert data["summary"]["open"] == 1
    assert [report["id"] for report in data["reports"]] == ["report-1"]


def test_admin_call_quality_returns_only_aggregate(monkeypatch):
    admin = User("Admin", 30, "admin@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [admin])
    monkeypatch.setattr(app, "load_call_signals", lambda: {
        "secret-room": {
            "status": "ended", "accepted_at": 100,
            "participants": ["alice@example.com", "bob@example.com"],
            "quality_summary": {
                "sample_count": 2, "relay_count": 2,
                "quality_counts": {"good": 1, "fair": 1, "poor": 0},
                "metrics": {name: {"p50": 10, "p95": 20} for name in (
                    "rtt_ms", "jitter_ms", "packet_loss_percent", "bitrate_kbps"
                )},
            },
        },
    })
    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = admin.email

    response = client.get("/api/admin/calls/quality")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["aggregate"]["room_count"] == 1
    assert payload["aggregate"]["turn_room_rate"] == 100
    assert "secret-room" not in str(payload)
    assert "alice@example.com" not in str(payload)


def test_admin_report_update_changes_status_and_saves(monkeypatch):
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

    response = client.patch(
        "/api/admin/moderation/reports/report-1",
        json={"status": "resolved", "note": "Handled", "action": "warning_sent"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["report"]["status"] == "resolved"
    assert data["report"]["reviewed_by"] == "admin@example.com"
    assert data["report"]["moderation_note"] == "Handled"
    assert data["report"]["action"] == "warning_sent"
    assert saved and saved[0]["reports"][0]["status"] == "resolved"


def test_admin_report_update_rejects_invalid_status(monkeypatch):
    admin = User("Admin", 30, "admin@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [admin])
    monkeypatch.setattr(app, "load_reports", lambda: {"reports": [{"id": "report-1"}]})
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com")

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = "admin@example.com"

    response = client.patch("/api/admin/moderation/reports/report-1", json={"status": "bad"})

    assert response.status_code == 400
    assert "Unsupported report status" in response.get_json()["error"]
