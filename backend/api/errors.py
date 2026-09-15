from flask import jsonify, request
from werkzeug.exceptions import HTTPException


def is_api_request():
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def api_error_response(message, status_code=400, code=None, details=None):
    payload = {
        "ok": False,
        "error": message,
        "status_code": status_code,
    }
    if code:
        payload["code"] = code
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def handle_http_exception(error):
    if is_api_request():
        code = error.code or 500
        message = error.name or error.description or "Request failed"
        return api_error_response(message, status_code=code, code=(error.name or "http_error").lower().replace(" ", "_"))
    return error


def handle_unexpected_error(error):
    if is_api_request():
        if isinstance(error, ValueError):
            return api_error_response(str(error) or "Invalid request", status_code=400, code="validation_error")
        return api_error_response("Internal server error", status_code=500, code="internal_server_error")
    raise error
