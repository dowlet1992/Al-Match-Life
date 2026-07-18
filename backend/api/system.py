from flask import Blueprint, current_app, jsonify


system_api = Blueprint("system_api", __name__)


@system_api.route("/api/health")
def api_health():
    return jsonify({
        "ok": True,
        "service": "AI Match Life",
        "status": "healthy",
        "routes": len(current_app.url_map._rules),
    })
