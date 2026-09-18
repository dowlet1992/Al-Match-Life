import json
import re
import secrets
import time

from flask import g, request


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")


def start_request_trace():
    supplied = str(request.headers.get("X-Request-ID") or "").strip()
    g.request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else secrets.token_hex(16)
    g.request_started_at = time.monotonic()


def finish_request_trace(response, logger):
    request_id = str(getattr(g, "request_id", "") or secrets.token_hex(16))
    started_at = getattr(g, "request_started_at", None)
    duration_ms = max(0, round((time.monotonic() - started_at) * 1000)) if started_at is not None else 0
    response.headers["X-Request-ID"] = request_id

    # Query strings, request/response bodies, session identifiers and user data
    # are deliberately excluded from the operational log contract.
    logger.info(json.dumps({
        "event": "http_request",
        "request_id": request_id,
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
    }, separators=(",", ":"), sort_keys=True))
    return response
