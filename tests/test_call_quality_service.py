from backend.services import call_quality_service


def test_quality_classification_uses_loss_latency_and_jitter():
    assert call_quality_service.classify_quality(100, 10, 1) == "good"
    assert call_quality_service.classify_quality(350, 10, 1) == "fair"
    assert call_quality_service.classify_quality(100, 80, 1) == "poor"


def test_quality_sample_is_bounded_and_contains_no_media_or_device_data():
    sample = call_quality_service.normalize_sample({
        "rtt_ms": float("inf"), "jitter_ms": -1, "packet_loss_percent": 200,
        "bitrate_kbps": "bad", "relay": True, "audio": "forbidden", "ip": "127.0.0.1",
    }, "Alice@Example.com", 100)

    assert sample["rtt_ms"] == 0
    assert sample["jitter_ms"] == 0
    assert sample["packet_loss_percent"] == 100
    assert sample["participant_email"] == "alice@example.com"
    assert "audio" not in sample
    assert "ip" not in sample


def test_room_quality_summary_and_aggregate_contain_no_identifiers():
    rooms = {
        "private-room-id": {
            "status": "ended",
            "accepted_at": 100,
            "messages": [{"type": "ended", "payload": {"reason": "connection_lost"}}],
            "quality_samples": [
                {"participant_email": "alice@example.com", "rtt_ms": 100, "jitter_ms": 10,
                 "packet_loss_percent": 1, "bitrate_kbps": 800, "quality": "good", "relay": True},
                {"participant_email": "bob@example.com", "rtt_ms": 900, "jitter_ms": 90,
                 "packet_loss_percent": 10, "bitrate_kbps": 200, "quality": "poor", "relay": True},
            ],
        },
        "declined-room": {"status": "declined", "messages": [{"type": "declined"}]},
    }

    aggregate = call_quality_service.aggregate_rooms(rooms)

    assert aggregate["room_count"] == 2
    assert aggregate["successful_room_count"] == 1
    assert aggregate["connection_success_rate"] == 50
    assert aggregate["turn_room_rate"] == 100
    assert aggregate["end_reasons"] == {"connection_lost": 1, "declined": 1}
    assert aggregate["quality_counts"] == {"fair": 0, "good": 1, "poor": 1}
    assert aggregate["metrics"]["rtt_ms"] == {"p50": 100, "p95": 900}
    serialized = str(aggregate)
    assert "alice@example.com" not in serialized
    assert "private-room-id" not in serialized
