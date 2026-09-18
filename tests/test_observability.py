import json
import logging

import app


def request_log(records):
    payloads = []
    for record in records:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("event") == "http_request":
            payloads.append(payload)
    return payloads[-1]


def test_request_id_is_returned_and_logged_without_query_or_sensitive_data(caplog):
    caplog.set_level(logging.INFO, logger=app.app.logger.name)

    response = app.app.test_client().get(
        "/api/health?token=must-not-be-logged&email=private@example.com",
        headers={"X-Request-ID": "release-check-123"},
    )

    assert response.headers["X-Request-ID"] == "release-check-123"
    payload = request_log(caplog.records)
    assert payload["request_id"] == "release-check-123"
    assert payload["path"] == "/api/health"
    assert payload["method"] == "GET"
    assert payload["status"] == 200
    assert isinstance(payload["duration_ms"], int)
    assert "token" not in json.dumps(payload)
    assert "private@example.com" not in json.dumps(payload)


def test_invalid_external_request_id_is_replaced(caplog):
    caplog.set_level(logging.INFO, logger=app.app.logger.name)

    response = app.app.test_client().get(
        "/api/health",
        headers={"X-Request-ID": "invalid id with spaces"},
    )

    request_id = response.headers["X-Request-ID"]
    assert request_id != "invalid id with spaces"
    assert len(request_id) == 32
    assert request_log(caplog.records)["request_id"] == request_id
