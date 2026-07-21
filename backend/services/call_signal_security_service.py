import threading
import time
import hashlib
import re


MAX_SIGNAL_REQUEST_BYTES = 64 * 1024
MAX_SDP_LENGTH = 32 * 1024
MAX_ICE_CANDIDATE_LENGTH = 2048
MAX_STATE_PAYLOAD_LENGTH = 2048
SIGNAL_RATE_LIMITS = {
    "ice": (120, 60),
    "offer": (10, 60),
    "answer": (10, 60),
    "ringing": (10, 60),
    "accepted": (10, 60),
    "ended": (6, 60),
    "declined": (6, 60),
    "missed": (6, 60),
}
EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,80}$")


def normalize_event_id(value):
    value = str(value or "").strip()
    return value if EVENT_ID_PATTERN.fullmatch(value) else ""


def normalize_ack_event_ids(values, maximum=50):
    if not isinstance(values, list) or not 1 <= len(values) <= maximum:
        return []
    normalized = []
    for value in values:
        value = str(value or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value):
            return []
        if value not in normalized:
            normalized.append(value)
    return normalized


def validate_signal_payload(signal_type, payload):
    if not isinstance(payload, dict):
        return None, "invalid_signal_payload"
    if signal_type in {"offer", "answer"}:
        sdp = payload.get("sdp")
        description_type = str(payload.get("type", ""))
        if not isinstance(sdp, str) or not sdp.startswith("v=0") or len(sdp) > MAX_SDP_LENGTH:
            return None, "invalid_session_description"
        if description_type != signal_type:
            return None, "invalid_session_description_type"
        return {"type": description_type, "sdp": sdp, "call_type": payload.get("call_type")}, None
    if signal_type == "ice":
        candidate = payload.get("candidate")
        if not isinstance(candidate, str) or not candidate.startswith("candidate:") or len(candidate) > MAX_ICE_CANDIDATE_LENGTH:
            return None, "invalid_ice_candidate"
        sdp_mid = payload.get("sdpMid")
        if sdp_mid is not None and (not isinstance(sdp_mid, str) or len(sdp_mid) > 64):
            return None, "invalid_ice_mid"
        line_index = payload.get("sdpMLineIndex")
        if line_index is not None and (not isinstance(line_index, int) or isinstance(line_index, bool) or not 0 <= line_index <= 64):
            return None, "invalid_ice_line_index"
        username_fragment = payload.get("usernameFragment")
        if username_fragment is not None and (not isinstance(username_fragment, str) or len(username_fragment) > 256):
            return None, "invalid_ice_username_fragment"
        return {
            "candidate": candidate,
            "sdpMid": sdp_mid,
            "sdpMLineIndex": line_index,
            "usernameFragment": username_fragment,
            "call_type": payload.get("call_type"),
        }, None
    if len(str(payload)) > MAX_STATE_PAYLOAD_LENGTH:
        return None, "signal_payload_too_large"
    allowed = {"call_type", "accepted_at", "declined_at", "ended_at", "missed_at", "reason"}
    normalized = {}
    for key, value in payload.items():
        if key not in allowed or not isinstance(value, (str, int, float, bool)):
            continue
        normalized[key] = value[:512] if isinstance(value, str) else value
    if normalized.get("reason") not in {None, "connection_lost"}:
        normalized.pop("reason", None)
    return normalized, None


class PollRateLimiter:
    def __init__(self, limit=120, window_seconds=60, max_keys=5000, repository=None):
        self.limit = int(limit)
        self.window_seconds = int(window_seconds)
        self.max_keys = int(max_keys)
        self.repository = repository
        self._events = {}
        self._lock = threading.RLock()

    def allow(self, key, now=None):
        now = float(now if now is not None else time.time())
        if self.repository is not None:
            key_hash = hashlib.sha256(f"call_signal_poll::{key}".encode("utf-8")).hexdigest()
            return self.repository.allow(
                key_hash, "call_signal_poll", self.limit, self.window_seconds, now,
            )
        cutoff = now - self.window_seconds
        with self._lock:
            events = [item for item in self._events.get(str(key), []) if item >= cutoff]
            if len(events) >= self.limit:
                self._events[str(key)] = events
                return False
            events.append(now)
            self._events[str(key)] = events
            if len(self._events) > self.max_keys:
                self._events = {
                    event_key: values for event_key, values in self._events.items()
                    if values and values[-1] >= cutoff
                }
            return True
