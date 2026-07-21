import hmac
import time
from datetime import datetime

from flask import Blueprint, jsonify, request


def create_call_signals_api(deps):
    api = Blueprint("mobile_call_signals_api", __name__)

    def fail(code, status=400, headers=None):
        response = jsonify({"ok": False, "error": code})
        response.status_code = status
        for key, value in (headers or {}).items():
            response.headers[key] = str(value)
        return response

    def context(call_id, data):
        user = deps["get_api_current_user"]()
        if user is None:
            return None, None, None, fail("authentication_required", 401)
        other_email = deps["normalize_email"](data.get("other_email", ""))
        call_type = deps["clean_text"](data.get("call_type", ""))
        if not other_email or call_type not in {"audio", "video"}:
            return None, None, None, fail("invalid_call_context")
        other = deps["find_user_by_email"](other_email)
        if other is None:
            return None, None, None, fail("user_not_found", 404)
        expected = deps["get_call_room_id"](user.email, other.email, call_type)
        if not hmac.compare_digest(deps["secure_call_id"](call_id), expected):
            return None, None, None, fail("forbidden_room", 403)
        if deps["is_blocked"](user.email, other.email) or deps["is_blocked"](other.email, user.email):
            return None, None, None, fail("call_unavailable", 403)
        if deps["is_restricted"](user.email, other.email) or deps["is_restricted"](other.email, user.email):
            return None, None, None, fail("call_unavailable", 403)
        return user, other, call_type, None

    @api.route("/api/calls/room", methods=["GET"])
    def resolve_room():
        user = deps["get_api_current_user"]()
        if user is None:
            return fail("authentication_required", 401)
        other_email = deps["normalize_email"](request.args.get("other_email", ""))
        call_type = deps["clean_text"](request.args.get("call_type", ""))
        other = deps["find_user_by_email"](other_email)
        if other is None:
            return fail("user_not_found", 404)
        if call_type not in {"audio", "video"}:
            return fail("invalid_call_context")
        if deps["is_blocked"](user.email, other.email) or deps["is_blocked"](other.email, user.email):
            return fail("call_unavailable", 403)
        if deps["is_restricted"](user.email, other.email) or deps["is_restricted"](other.email, user.email):
            return fail("call_unavailable", 403)
        return jsonify({"ok": True, "call_id": deps["get_call_room_id"](user.email, other.email, call_type),
                        "call_type": call_type, "other_email": deps["normalize_email"](other.email)})

    @api.route("/api/calls/<call_id>/signals", methods=["GET", "POST"])
    def signals(call_id):
        if request.content_length is not None and request.content_length > deps["security"].MAX_SIGNAL_REQUEST_BYTES:
            return fail("signal_request_too_large", 413)
        data = request.args if request.method == "GET" else request.get_json(silent=True)
        if not hasattr(data, "get"):
            return fail("invalid_signal_request")
        user, other, call_type, error = context(call_id, data)
        if error:
            return error
        room_id = deps["get_call_room_id"](user.email, other.email, call_type)

        if request.method == "GET":
            if not deps["poll_limiter"].allow(f"mobile::{user.email}::{room_id}"):
                return fail("signal_poll_rate_limited", 429, {"Retry-After": "1"})
            timeout_result = deps["expire_room"](room_id, time.time())
            room = timeout_result.get("room") if isinstance(timeout_result, dict) else deps["get_room"](room_id)
            room = room if isinstance(room, dict) else {"messages": [], "status": "active"}
            transition = timeout_result.get("transition") if isinstance(timeout_result, dict) else None
            if isinstance(transition, dict):
                payload = transition.get("payload", {}) if isinstance(transition.get("payload"), dict) else {}
                deps["record_history"](transition.get("from", ""), transition.get("to", ""), payload.get("call_type", call_type), transition.get("type", "ended"))
            try:
                after = float(data.get("after", 0) or 0)
            except (TypeError, ValueError):
                after = 0
            messages, acknowledged = [], []
            for item in room.get("messages", []) if isinstance(room.get("messages"), list) else []:
                if not isinstance(item, dict):
                    continue
                sender = deps["normalize_email"](item.get("from", ""))
                ack_by = deps["normalize_email"](item.get("acknowledged_by", ""))
                if sender == deps["normalize_email"](user.email):
                    if ack_by and item.get("id"):
                        acknowledged.append(str(item["id"]))
                    continue
                try:
                    created_at = float(item.get("created_at", 0) or 0)
                except (TypeError, ValueError):
                    created_at = 0
                if created_at <= after and (not item.get("id") or ack_by == deps["normalize_email"](user.email)):
                    continue
                messages.append(item)
            return jsonify({"ok": True, "status": room.get("status", "active"), "messages": messages,
                            "acknowledged_event_ids": acknowledged[-100:], "server_time": time.time()})

        deps["validate_write_request"]()
        signal_type = deps["clean_text"](data.get("type", ""))
        event_id = deps["security"].normalize_event_id(data.get("event_id", ""))
        if signal_type not in {"offer", "answer", "ice", "ringing", "accepted", "declined", "ended"}:
            return fail("invalid_signal_type")
        if not event_id:
            return fail("invalid_signal_event_id")
        signal_payload, payload_error = deps["security"].validate_signal_payload(signal_type, data.get("payload", {}))
        if payload_error:
            return fail(payload_error)
        now = time.time()
        message = {"id": event_id, "type": signal_type, "from": deps["normalize_email"](user.email),
                   "to": deps["normalize_email"](other.email), "payload": signal_payload, "created_at": now}
        existing_room = deps["get_room"](room_id) or {"messages": []}
        push_event = None
        if signal_type == "ringing":
            push_event = {"event_id": event_id, "target_email": other.email, "event_type": "incoming_call",
                          "payload": {"call_id": room_id, "call_type": call_type, "caller_email": user.email, "receiver_email": other.email},
                          "created_at": now, "expires_at": now + 45, "attempts": 0, "status": "pending"}
        elif signal_type in {"declined", "ended"}:
            push_event = deps["cancel_push_event"](room_id, existing_room, message, now)
        closed = signal_type in {"declined", "ended"}
        limit, window = deps["security"].SIGNAL_RATE_LIMITS[signal_type]
        stored = deps["append_signal"](room_id, message, status=signal_type if closed else "active",
                                        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), close=closed,
                                        rate_limit=limit, rate_window=window, enforce_transition=True, push_event=push_event)
        if stored == "rate_limited": return fail("signal_rate_limited", 429, {"Retry-After": "1"})
        if stored == "invalid_transition": return fail("invalid_call_transition", 409)
        if stored == "idempotency_conflict": return fail("signal_idempotency_conflict", 409)
        if not isinstance(stored, dict): return fail("signal_not_persisted", 409)
        duplicate = isinstance(stored, dict) and stored.pop("_signal_duplicate", False) is True
        if closed and isinstance(stored, dict) and not duplicate:
            deps["record_history"](user.email, other.email, call_type, signal_type)
        return jsonify({"ok": True, "event_id": event_id, "duplicate": duplicate})

    @api.route("/api/calls/<call_id>/signals/ack", methods=["POST"])
    def acknowledge(call_id):
        if request.content_length is not None and request.content_length > deps["security"].MAX_SIGNAL_REQUEST_BYTES:
            return fail("signal_request_too_large", 413)
        data = request.get_json(silent=True)
        if not isinstance(data, dict): return fail("invalid_ack_request")
        user, other, call_type, error = context(call_id, data)
        if error: return error
        deps["validate_write_request"]()
        event_ids = deps["security"].normalize_ack_event_ids(data.get("event_ids"))
        if not event_ids: return fail("invalid_ack_request")
        room_id = deps["get_call_room_id"](user.email, other.email, call_type)
        if not deps["poll_limiter"].allow(f"mobile-ack::{user.email}::{room_id}"):
            return fail("signal_ack_rate_limited", 429, {"Retry-After": "1"})
        status, count = deps["acknowledge"](room_id, user.email, event_ids, time.time())
        if status == "missing": return fail("call_room_not_found", 404)
        return jsonify({"ok": True, "acknowledged_event_ids": event_ids, "acknowledged_count": count})

    return api
