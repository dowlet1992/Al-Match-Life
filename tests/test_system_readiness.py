import app
from backend.api import system


def test_readiness_reports_real_component_state(monkeypatch):
    monkeypatch.setattr(system, "provider_status", lambda environ, check_connection: {
        "enabled": True, "provider": "ollama", "model": "test-model",
    })
    monkeypatch.setattr(system, "speech_provider_available", lambda environ: True)
    monkeypatch.setattr(system, "build_production_readiness_report", lambda environ: {
        "ready_for_production": False,
    })

    response = app.app.test_client().get("/api/readiness")
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert data["components"]["ai"] == {
        "ready": True, "provider": "ollama", "model": "test-model",
    }
    assert data["components"]["speech"]["ready"] is True
    assert response.headers["Cache-Control"] == "no-store"


def test_readiness_returns_503_when_ai_is_unavailable(monkeypatch):
    monkeypatch.setattr(system, "provider_status", lambda environ, check_connection: {
        "enabled": False, "provider": "ollama", "model": "test-model",
    })
    monkeypatch.setattr(system, "speech_provider_available", lambda environ: True)

    response = app.app.test_client().get("/api/readiness")

    assert response.status_code == 503
    assert response.get_json()["status"] == "not_ready"


def test_liveness_stays_fast_and_independent_of_ai(monkeypatch):
    monkeypatch.setattr(system, "provider_status", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    response = app.app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"
