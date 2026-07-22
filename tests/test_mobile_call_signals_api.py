import time

import app
from backend.auth_tokens import create_access_token
from backend.models import User


def bearer(email):
    token = create_access_token(email, app.app.secret_key, issued_at=int(time.time()), expires_in_seconds=3600, session_version=1)
    return {"Authorization": f"Bearer {token}"}


def users(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "DE", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "DE", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "is_blocked", lambda *args: False)
    monkeypatch.setattr(app, "is_restricted", lambda *args: False)
    return alice, bob


def test_mobile_call_signals_require_authentication(monkeypatch):
    alice, bob = users(monkeypatch)
    room = app.get_call_room_id(alice.email, bob.email, "audio")
    response = app.app.test_client().get(f"/api/calls/{room}/signals?other_email={bob.email}&call_type=audio")
    assert response.status_code == 401


def test_mobile_bearer_can_ring_with_transactional_push(monkeypatch):
    alice, bob = users(monkeypatch)
    room = app.get_call_room_id(alice.email, bob.email, "video")
    captured = []
    monkeypatch.setattr(app, "get_call_signal_room", lambda room_id: None)
    def append(room_id, signal, **options):
        captured.append((room_id, signal, options))
        return {"status": "active", "messages": [signal]}
    monkeypatch.setattr(app, "append_call_signal", append)

    response = app.app.test_client().post(f"/api/calls/{room}/signals", headers=bearer(alice.email), json={
        "other_email": bob.email, "call_type": "video", "type": "ringing",
        "event_id": "mobile_ring_1234567890", "payload": {"call_type": "video"},
    })

    assert response.status_code == 200
    assert response.get_json()["duplicate"] is False
    assert captured[0][1]["from"] == alice.email
    assert captured[0][2]["push_event"]["target_email"] == bob.email
    assert captured[0][2]["push_event"]["event_type"] == "incoming_call"


def test_mobile_resolves_canonical_call_room(monkeypatch):
    alice, bob = users(monkeypatch)
    response = app.app.test_client().get(
        f"/api/calls/room?other_email={bob.email}&call_type=video", headers=bearer(alice.email),
    )
    assert response.status_code == 200
    assert response.get_json()["call_id"] == app.get_call_room_id(alice.email, bob.email, "video")


def test_mobile_restores_exact_incoming_call_context(monkeypatch):
    alice, bob = users(monkeypatch)
    room = app.get_call_room_id(alice.email, bob.email, "video")
    now = time.time()
    monkeypatch.setattr(app, "expire_call_signal_room", lambda *args: {"transition": None, "room": {
        "status": "active", "messages": [{
            "id": "mobile_ring_1234567890", "type": "ringing", "from": alice.email, "to": bob.email,
            "created_at": now, "payload": {"call_type": "video"},
        }],
    }})

    response = app.app.test_client().get(
        f"/api/calls/{room}/context?call_type=video&event_id=mobile_ring_1234567890",
        headers=bearer(bob.email),
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.get_json() == {
        "ok": True, "event_id": "mobile_ring_1234567890", "event_type": "incoming_call",
        "call_id": room, "call_type": "video", "caller_email": alice.email,
        "receiver_email": bob.email, "expires_at": int(now + 180),
    }


def test_mobile_rejects_stale_or_mismatched_incoming_call_context(monkeypatch):
    alice, bob = users(monkeypatch)
    room = app.get_call_room_id(alice.email, bob.email, "audio")
    monkeypatch.setattr(app, "expire_call_signal_room", lambda *args: {"transition": None, "room": {
        "status": "active", "messages": [{
            "id": "mobile_ring_1234567890", "type": "ringing", "from": alice.email, "to": bob.email,
            "created_at": time.time() - 181, "payload": {"call_type": "audio"},
        }],
    }})

    stale = app.app.test_client().get(
        f"/api/calls/{room}/context?call_type=audio&event_id=mobile_ring_1234567890",
        headers=bearer(bob.email),
    )
    wrong_event = app.app.test_client().get(
        f"/api/calls/{room}/context?call_type=audio&event_id=mobile_ring_0987654321",
        headers=bearer(bob.email),
    )

    assert stale.status_code == 404
    assert wrong_event.status_code == 404


def test_mobile_bootstrap_exposes_honest_translation_and_call_contract(monkeypatch):
    alice, bob = users(monkeypatch)
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_server_call_transcription": True,
        "auto_translate_call_captions": True, "auto_translate_messages": True,
        "allow_ai_voice_translation": True,
        "message_translation_language": "de", "call_spoken_language": "auto", "call_caption_language": "en",
    })
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    response = app.app.test_client().get("/api/mobile/bootstrap", headers=bearer(alice.email))
    data = response.get_json()
    assert response.status_code == 200
    assert data["features"]["live_call_captions"] is True
    assert data["features"]["transcription_provider_available"] is True
    assert data["features"]["ai_voice_translation_consent"] is True
    assert data["features"]["realtime_speech_provider_available"] is True
    assert data["languages"]["call_spoken"] == "auto"
    assert data["call_contract"]["incoming_context_endpoint_template"] == "/api/calls/{call_id}/context"
    assert data["call_contract"]["signals_endpoint_template"] == "/api/calls/{call_id}/signals"
    assert data["call_contract"]["realtime_session_endpoint_template"].endswith("/translation/realtime-session")
    speech_contract = data["speech_translation_contract"]
    assert speech_contract["version"] == 1
    assert speech_contract["transitions"]["streaming"] == ["fallback", "stopping", "failed"]
    assert speech_contract["audio_policy"]["voice_cloning"] is False
    assert speech_contract["security"]["provider_api_key_exposed"] is False
    assert "OPENAI_API_KEY" not in str(data)


def test_mobile_signal_poll_delivers_only_remote_events(monkeypatch):
    alice, bob = users(monkeypatch)
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    room = {"status": "active", "messages": [
        {"id": "remote_1234567890", "type": "offer", "from": alice.email, "to": bob.email, "created_at": 100},
        {"id": "local_12345678901", "type": "accepted", "from": bob.email, "to": alice.email, "created_at": 101},
    ]}
    monkeypatch.setattr(app, "expire_call_signal_room", lambda *args: {"transition": None, "room": room})

    response = app.app.test_client().get(
        f"/api/calls/{room_id}/signals?other_email={alice.email}&call_type=audio&after=0",
        headers=bearer(bob.email),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.get_json()["messages"]] == ["remote_1234567890"]


def test_mobile_signal_ack_uses_bearer_without_csrf(monkeypatch):
    alice, bob = users(monkeypatch)
    room = app.get_call_room_id(alice.email, bob.email, "audio")
    monkeypatch.setattr(app, "acknowledge_call_signals", lambda *args: ("acknowledged", 1))

    response = app.app.test_client().post(f"/api/calls/{room}/signals/ack", headers=bearer(bob.email), json={
        "other_email": alice.email, "call_type": "audio", "event_ids": ["remote_1234567890"],
    })

    assert response.status_code == 200
    assert response.get_json()["acknowledged_count"] == 1


def test_mobile_call_room_cannot_be_guessed(monkeypatch):
    alice, bob = users(monkeypatch)
    response = app.app.test_client().get(
        f"/api/calls/not-a-room/signals?other_email={bob.email}&call_type=audio",
        headers=bearer(alice.email),
    )
    assert response.status_code == 403
