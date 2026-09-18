import os

from flask import Blueprint, current_app, jsonify

from backend.config import build_production_readiness_report
from backend.ai_provider import provider_status
from backend.database import PostgresClient, load_database_settings
from backend.services.speech_transcription_service import provider_available as speech_provider_available


system_api = Blueprint("system_api", __name__)


def database_status(environ=None):
    settings = load_database_settings(environ)
    if not settings.postgres_enabled:
        return {"ready": True, "backend": settings.storage_backend}
    if not settings.database_url:
        return {"ready": False, "backend": settings.storage_backend}

    try:
        with PostgresClient(settings).connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row = cursor.fetchone()
        ready = bool(row and row[0] == 1)
    except Exception:
        ready = False
    return {"ready": ready, "backend": settings.storage_backend}


@system_api.route("/api/health")
def api_health():
    environment = os.environ.get("FLASK_ENV") or os.environ.get("APP_ENV") or "development"
    storage_backend = (os.environ.get("STORAGE_BACKEND") or "json").strip().lower() or "json"
    production_report = build_production_readiness_report(os.environ)

    database_configured = storage_backend != "postgres" or bool(str(os.environ.get("DATABASE_URL") or "").strip())

    return jsonify({
        "ok": True,
        "service": "NOVIX",
        "status": "healthy",
        "environment": environment,
        "storage_backend": storage_backend,
        "database_configured": database_configured,
        "production_ready": bool(production_report.get("ready_for_production", False)),
        "routes": len(current_app.url_map._rules),
    })


@system_api.route("/api/readiness")
def api_readiness():
    """Dependency-aware readiness check; safe for deploy probes and diagnostics."""
    database = database_status(os.environ)
    ai = provider_status(os.environ, check_connection=True)
    speech_ready = speech_provider_available(os.environ)
    production_report = build_production_readiness_report(os.environ)
    application_ready = bool(database["ready"]) and bool(ai.get("enabled")) and speech_ready

    response = jsonify({
        "ok": application_ready,
        "status": "ready" if application_ready else "not_ready",
        "components": {
            "database": database,
            "ai": {
                "ready": bool(ai.get("enabled")),
                "provider": ai.get("provider", ""),
                "model": ai.get("model", ""),
            },
            "speech": {"ready": speech_ready},
        },
        "production_ready": bool(production_report.get("ready_for_production", False)),
    })
    response.status_code = 200 if application_ready else 503
    response.headers["Cache-Control"] = "no-store"
    return response
