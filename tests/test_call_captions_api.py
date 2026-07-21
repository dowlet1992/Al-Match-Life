import io

import app
from backend.models import User


def login(client, email):
    with client.session_transaction() as session:
        session["user_email"] = email


def test_call_captions_require_opt_in(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"live_call_captions": False})
    client = app.app.test_client()
    login(client, alice.email)
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")

    response = client.get(f"/api/calls/{room_id}/captions?other_email={bob.email}&call_type=audio")

    assert response.status_code == 403


def test_call_participants_can_publish_and_poll_captions(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "video")
    signals = {room_id: {"status": "active", "messages": [], "captions": []}}
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"live_call_captions": True, "allow_server_call_transcription": True})
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: signals.get(selected_room))
    def append_caption(selected_room, segment, **options):
        app.call_caption_service.append_segment(signals[selected_room], segment)
        return "appended"
    monkeypatch.setattr(app, "append_call_caption", append_caption)

    alice_client = app.app.test_client()
    login(alice_client, alice.email)
    created = alice_client.post(f"/api/calls/{room_id}/captions", json={
        "other_email": bob.email, "call_type": "video", "text": "Hello Bob",
        "source_language": "en", "is_final": True, "sequence": 1,
    })

    bob_client = app.app.test_client()
    login(bob_client, bob.email)
    polled = bob_client.get(f"/api/calls/{room_id}/captions?other_email={alice.email}&call_type=video")

    assert created.status_code == 201
    assert polled.status_code == 200
    assert polled.get_json()["captions"][0]["text"] == "Hello Bob"


def test_call_caption_room_cannot_be_guessed(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/api/calls/not-the-room/captions?other_email={bob.email}&call_type=audio")

    assert response.status_code == 403


def test_call_participant_receives_private_ice_configuration(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app.turn_credential_service, "get_ice_configuration", lambda cache_key: {
        "ice_servers": [{"urls": "turn:relay.example.com", "username": "temporary", "credential": "ephemeral"}],
        "provider": "twilio", "ttl": 3600, "expires_at": 1234, "cached": False,
    })
    client = app.app.test_client()
    login(client, alice.email)
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")

    response = client.get(f"/api/calls/{room_id}/ice-servers?other_email={bob.email}&call_type=audio")

    assert response.status_code == 200
    assert response.get_json()["ice_servers"][0]["credential"] == "ephemeral"
    assert response.headers["Cache-Control"] == "no-store, private"
    assert response.headers["Pragma"] == "no-cache"


def test_ice_configuration_rejects_guessed_room(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.get(f"/api/calls/guessed-room/ice-servers?other_email={bob.email}&call_type=audio")

    assert response.status_code == 403


def test_active_call_accepts_bounded_quality_aggregate(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "video")
    captured = []
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: {"status": "active"})
    monkeypatch.setattr(app, "append_call_quality_sample", lambda selected_room, sample, **options: captured.append(sample) or "appended")
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(f"/api/calls/{room_id}/quality", json={
        "other_email": bob.email, "call_type": "video", "rtt_ms": 900,
        "jitter_ms": 120, "packet_loss_percent": 150, "bitrate_kbps": -5, "relay": True,
    })

    assert response.status_code == 201
    assert response.get_json()["quality"] == "poor"
    assert captured[0]["packet_loss_percent"] == 100
    assert captured[0]["bitrate_kbps"] == 0
    assert captured[0]["relay"] is True
    assert set(captured[0]) == {
        "participant_email", "rtt_ms", "jitter_ms", "packet_loss_percent",
        "bitrate_kbps", "quality", "relay", "created_at",
    }


def test_call_caption_translation_is_cached_without_replacing_original(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    room = {"status": "active", "captions": [{
        "id": "caption-1", "speaker_email": bob.email, "text": "Hallo",
        "source_language": "de", "is_final": True, "translations": {}, "created_at": 100,
    }]}
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "call_caption_language": "en",
    })
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: room)
    monkeypatch.setattr(app, "translate_message_text", lambda text, source, target: "Hello")
    def save_translation(selected_room, caption_id, language, text):
        room["captions"][0]["translations"][language] = text
        return "updated"
    monkeypatch.setattr(app, "set_call_caption_translation", save_translation)
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(f"/api/calls/{room_id}/captions/caption-1/translation", json={
        "other_email": bob.email, "call_type": "audio", "target_language": "en",
    })

    assert response.status_code == 200
    assert response.get_json()["translation"]["translated_text"] == "Hello"
    assert room["captions"][0]["text"] == "Hallo"
    assert room["captions"][0]["translations"] == {"en": "Hello"}


def test_server_transcription_creates_caption_without_persisting_audio(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    room = {"status": "active", "captions": []}
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"live_call_captions": True, "allow_server_call_transcription": True})
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: room)
    monkeypatch.setattr(
        app.speech_transcription_service, "transcribe_audio_chunk",
        lambda audio, content_type, language: {"ok": True, "text": "Server transcript", "model": "test-model", "detected_language": "de"},
    )
    captured = []
    monkeypatch.setattr(app, "append_call_caption", lambda selected_room, segment, **options: captured.append(segment) or "appended")
    monkeypatch.setattr(app, "reserve_call_transcription", lambda *args, **kwargs: "reserved")
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/api/calls/{room_id}/captions/transcribe",
        data={
            "other_email": bob.email, "call_type": "audio", "source_language": "en",
            "sequence": "2", "audio": (io.BytesIO(b"\x1a\x45\xdf\xa3audio-data"), "chunk.webm", "audio/webm"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    assert captured[0]["text"] == "Server transcript"
    assert captured[0]["source_language"] == "de"
    assert "audio" not in captured[0]


def test_server_transcription_requires_separate_audio_provider_consent(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_server_call_transcription": False,
    })
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/api/calls/{room_id}/captions/transcribe",
        data={"other_email": bob.email, "call_type": "audio", "sequence": "1",
              "audio": (io.BytesIO(b"\x1a\x45\xdf\xa3audio-data"), "chunk.webm", "audio/webm")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "Server transcription consent is required"


def test_server_transcription_rejects_duplicate_before_provider_call(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"live_call_captions": True, "allow_server_call_transcription": True})
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: {"status": "active"})
    monkeypatch.setattr(app, "reserve_call_transcription", lambda *args, **kwargs: "duplicate")
    provider_calls = []
    monkeypatch.setattr(app.speech_transcription_service, "transcribe_audio_chunk", lambda *args: provider_calls.append(args))
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/api/calls/{room_id}/captions/transcribe",
        data={"other_email": bob.email, "call_type": "audio", "sequence": "1",
              "audio": (io.BytesIO(b"\x1a\x45\xdf\xa3audio-data"), "chunk.webm", "audio/webm")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 409
    assert provider_calls == []


def test_server_transcription_returns_retry_after_when_rate_limited(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "video")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"live_call_captions": True, "allow_server_call_transcription": True})
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: {"status": "active"})
    monkeypatch.setattr(app, "reserve_call_transcription", lambda *args, **kwargs: "rate_limited")
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/api/calls/{room_id}/captions/transcribe",
        data={"other_email": bob.email, "call_type": "video", "sequence": "19",
              "audio": (io.BytesIO(b"\x1a\x45\xdf\xa3audio-data"), "chunk.webm", "audio/webm")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "4"


def test_server_transcription_rejects_large_request_before_form_parsing(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    monkeypatch.setattr(app, "users", [alice, bob])
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(
        f"/api/calls/{room_id}/captions/transcribe",
        data=b"x",
        content_type="multipart/form-data; boundary=test",
        environ_overrides={
            "CONTENT_LENGTH": str(app.speech_transcription_service.MAX_TRANSCRIPTION_REQUEST_BYTES + 1),
        },
    )

    assert response.status_code == 413


def test_active_participant_can_mint_no_store_realtime_session(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_server_call_transcription": True, "call_spoken_language": "de",
    })
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: {"status": "active"})
    monkeypatch.setattr(app.call_speech_limiter, "allow", lambda key: True)
    monkeypatch.setattr(app.realtime_speech_service, "create_transcription_session", lambda language: {
        "ok": True, "client_secret": "ek-temporary", "expires_at": 1900000000,
        "model": "test-realtime", "transcription_model": "test-transcribe", "transport": "webrtc",
        "calls_endpoint": "https://api.openai.com/v1/realtime/calls",
    })
    client = app.app.test_client()
    login(client, alice.email)

    response = client.post(f"/api/calls/{room_id}/translation/realtime-session", json={
        "other_email": bob.email, "call_type": "audio",
    })

    assert response.status_code == 200
    assert response.get_json()["session"]["client_secret"] == "ek-temporary"
    assert response.headers["Cache-Control"] == "no-store, private"
    assert "OPENAI_API_KEY" not in response.get_data(as_text=True)


def test_realtime_session_requires_transcription_consent(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "video")
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_server_call_transcription": False,
    })
    client = app.app.test_client()
    login(client, alice.email)
    response = client.post(f"/api/calls/{room_id}/translation/realtime-session", json={
        "other_email": bob.email, "call_type": "video",
    })
    assert response.status_code == 403


def test_translated_speech_requires_consent_and_uses_remote_caption(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    room_id = app.get_call_room_id(alice.email, bob.email, "audio")
    room = {"status": "active", "captions": [{
        "id": "remote-caption", "speaker_email": bob.email, "text": "Hallo",
        "source_language": "de", "translations": {}, "created_at": 1,
    }]}
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_ai_voice_translation": True, "call_caption_language": "en",
    })
    monkeypatch.setattr(app, "get_call_signal_room", lambda selected_room: room)
    translation_calls = []
    monkeypatch.setattr(app, "translate_message_text", lambda text, source, target: translation_calls.append(text) or "Hello")
    monkeypatch.setattr(
        app, "set_call_caption_translation",
        lambda selected_room, caption_id, language, text: room["captions"][0]["translations"].__setitem__(language, text) or "updated",
    )
    monkeypatch.setattr(app.call_speech_limiter, "allow", lambda key: True)
    monkeypatch.setattr(app.realtime_speech_service, "synthesize_speech", lambda text, voice: {
        "ok": True, "audio": b"ID3translated", "content_type": "audio/mpeg", "voice": voice,
    })
    client = app.app.test_client()
    login(client, alice.email)
    response = client.post(f"/api/calls/{room_id}/captions/remote-caption/speech", json={
        "other_email": bob.email, "call_type": "audio", "voice": "coral",
    })
    repeated = client.post(f"/api/calls/{room_id}/captions/remote-caption/speech", json={
        "other_email": bob.email, "call_type": "audio", "voice": "coral",
    })
    assert response.status_code == 200
    assert response.data == b"ID3translated"
    assert response.headers["X-AI-Generated-Voice"] == "true"
    assert response.headers["X-AI-Voice"] == "coral"
    assert response.headers["X-Caption-Id"] == "remote-caption"
    assert response.headers["Content-Language"] == "en"
    assert response.headers["Cache-Control"] == "no-store, private"
    assert room["captions"][0]["translations"] == {"en": "Hello"}
    assert translation_calls == ["Hallo"]
    assert repeated.status_code == 200
