import app
from backend.api import system


def test_readiness_reports_real_component_state(monkeypatch):
    monkeypatch.setattr(system, "database_status", lambda environ: {
        "ready": True, "backend": "postgres",
    })
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
    assert data["components"]["database"] == {"ready": True, "backend": "postgres"}
    assert response.headers["Cache-Control"] == "no-store"


def test_readiness_returns_503_when_ai_is_unavailable(monkeypatch):
    monkeypatch.setattr(system, "database_status", lambda environ: {
        "ready": True, "backend": "postgres",
    })
    monkeypatch.setattr(system, "provider_status", lambda environ, check_connection: {
        "enabled": False, "provider": "ollama", "model": "test-model",
    })
    monkeypatch.setattr(system, "speech_provider_available", lambda environ: True)

    response = app.app.test_client().get("/api/readiness")

    assert response.status_code == 503
    assert response.get_json()["status"] == "not_ready"


def test_readiness_returns_503_when_database_probe_fails(monkeypatch):
    monkeypatch.setattr(system, "database_status", lambda environ: {
        "ready": False, "backend": "postgres",
    })
    monkeypatch.setattr(system, "provider_status", lambda environ, check_connection: {
        "enabled": True, "provider": "ollama", "model": "test-model",
    })
    monkeypatch.setattr(system, "speech_provider_available", lambda environ: True)

    response = app.app.test_client().get("/api/readiness")

    assert response.status_code == 503
    assert response.get_json()["components"]["database"] == {
        "ready": False, "backend": "postgres",
    }


def test_liveness_stays_fast_and_independent_of_ai(monkeypatch):
    monkeypatch.setattr(system, "provider_status", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    response = app.app.test_client().get("/api/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_database_status_accepts_json_without_external_probe():
    assert system.database_status({"STORAGE_BACKEND": "json"}) == {
        "ready": True,
        "backend": "json",
    }


def test_database_status_rejects_postgres_without_url():
    assert system.database_status({"STORAGE_BACKEND": "postgres"}) == {
        "ready": False,
        "backend": "postgres",
    }


def test_database_status_runs_bounded_postgres_query(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            assert query == "SELECT 1"

        def fetchone(self):
            return (1,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return Cursor()

    class Client:
        def __init__(self, settings):
            assert settings.connect_timeout_seconds == 2

        def connect(self):
            return Connection()

    monkeypatch.setattr(system, "PostgresClient", Client)

    assert system.database_status({
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://novix:secret@db/novix",
        "DATABASE_CONNECT_TIMEOUT": "2",
    }) == {"ready": True, "backend": "postgres"}


def test_database_status_fails_closed_without_leaking_exception(monkeypatch):
    class Client:
        def __init__(self, _settings):
            pass

        def connect(self):
            raise RuntimeError("postgresql://novix:secret@db/novix")

    monkeypatch.setattr(system, "PostgresClient", Client)

    assert system.database_status({
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://novix:secret@db/novix",
    }) == {"ready": False, "backend": "postgres"}
