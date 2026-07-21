from backend.services import call_signal_security_service


def test_sdp_validation_requires_matching_type_and_bounds():
    valid, error = call_signal_security_service.validate_signal_payload(
        "offer", {"type": "offer", "sdp": "v=0\r\nt=0 0", "call_type": "video", "ignored": "value"},
    )
    assert error is None
    assert valid == {"type": "offer", "sdp": "v=0\r\nt=0 0", "call_type": "video"}

    assert call_signal_security_service.validate_signal_payload(
        "offer", {"type": "answer", "sdp": "v=0"},
    )[1] == "invalid_session_description_type"
    assert call_signal_security_service.validate_signal_payload(
        "offer", {"type": "offer", "sdp": "v=0" + "x" * call_signal_security_service.MAX_SDP_LENGTH},
    )[1] == "invalid_session_description"


def test_ice_validation_rejects_invalid_shape():
    valid, error = call_signal_security_service.validate_signal_payload("ice", {
        "candidate": "candidate:1 1 UDP 1 192.0.2.1 5000 typ host",
        "sdpMid": "0", "sdpMLineIndex": 0, "usernameFragment": "short",
    })
    assert error is None
    assert valid["candidate"].startswith("candidate:")
    assert call_signal_security_service.validate_signal_payload(
        "ice", {"candidate": "not-a-candidate"},
    )[1] == "invalid_ice_candidate"
    assert call_signal_security_service.validate_signal_payload(
        "ice", {"candidate": "candidate:x", "sdpMLineIndex": True},
    )[1] == "invalid_ice_line_index"


def test_state_payload_is_allowlisted_and_reason_is_fixed():
    valid, error = call_signal_security_service.validate_signal_payload("ended", {
        "call_type": "audio", "reason": "custom-user-text", "nested": {"secret": True},
    })
    assert error is None
    assert valid == {"call_type": "audio"}


def test_signal_event_id_has_strict_transport_safe_format():
    assert call_signal_security_service.normalize_event_id("event_1234567890-abcd") == "event_1234567890-abcd"
    assert call_signal_security_service.normalize_event_id("short") == ""
    assert call_signal_security_service.normalize_event_id("x" * 81) == ""
    assert call_signal_security_service.normalize_event_id("event id with spaces") == ""


def test_ack_event_ids_are_bounded_deduplicated_and_legacy_compatible():
    assert call_signal_security_service.normalize_ack_event_ids([
        "event_1234567890", "event_1234567890", "legacy_01",
    ]) == ["event_1234567890", "legacy_01"]
    assert call_signal_security_service.normalize_ack_event_ids([]) == []
    assert call_signal_security_service.normalize_ack_event_ids(["short"]) == []
    assert call_signal_security_service.normalize_ack_event_ids(["event_1234567890"] * 51) == []


def test_poll_rate_limiter_uses_bounded_sliding_window():
    limiter = call_signal_security_service.PollRateLimiter(limit=2, window_seconds=10)
    assert limiter.allow("room", now=100) is True
    assert limiter.allow("room", now=101) is True
    assert limiter.allow("room", now=102) is False
    assert limiter.allow("room", now=111) is True


def test_poll_rate_limiter_hashes_identity_for_distributed_repository():
    calls = []

    class Repository:
        def allow(self, *args):
            calls.append(args)
            return True

    limiter = call_signal_security_service.PollRateLimiter(
        limit=120, window_seconds=60, repository=Repository(),
    )

    assert limiter.allow("alice@example.com::private-room", now=100) is True
    key_hash, category, limit, window, now = calls[0]
    assert len(key_hash) == 64
    assert "alice@example.com" not in key_hash
    assert "private-room" not in key_hash
    assert (category, limit, window, now) == ("call_signal_poll", 120, 60, 100)
