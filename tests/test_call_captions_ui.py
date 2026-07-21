import app
from backend.models import User


def test_call_page_renders_opt_in_caption_controls(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_server_call_transcription": True,
        "allow_ai_voice_translation": True,
        "auto_translate_call_captions": True, "call_caption_language": "en", "call_spoken_language": "de",
    })
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    response = client.get(f"/audio_call/{alice.email}/{bob.email}")

    assert response.status_code == 200
    assert b'id="captionsBtn"' in response.data
    assert b'id="captionPanel"' in response.data
    assert b"const captionsAllowed = true" in response.data
    assert b"window.SpeechRecognition || window.webkitSpeechRecognition" in response.data
    assert b'const recognitionLanguage = "de"' in response.data
    assert b"/api/calls/" in response.data
    assert b"const autoTranslateCaptions = true" in response.data
    assert b"const serverTranscriptionAllowed = true" in response.data
    assert b"const aiVoiceTranslationAllowed = true" in response.data
    assert b'/static/realtime-caption-client.js' in response.data
    assert b"startRealtimeCaptions" in response.data
    assert b"enqueueTranslatedSpeech" in response.data
    assert b"X-AI-Generated-Voice" in response.data
    assert b"remoteMedia.volume = Math.min(previousVolume, 0.28)" in response.data
    assert b"stopTranslatedSpeech()" in response.data
    assert b"translateRemoteCaption" in response.data
    assert b"startServerCaptionCycle" in response.data
    assert b"MediaRecorder" in response.data
    assert b"/transcribe" in response.data
    assert b"response.headers.get('Retry-After')" in response.data
    assert b"serverCaptionFailures >= 3" in response.data
    assert b"const maxReconnectAttempts = 3" in response.data
    assert b"createOffer({iceRestart: true})" in response.data
    assert b"peerConnection.restartIce" in response.data
    assert b"scheduleReconnect(5000)" in response.data
    assert b"reason: 'connection_lost'" in response.data
    assert b"window.addEventListener('offline'" in response.data
    assert b"window.addEventListener('online'" in response.data
    assert b"const processedSignalIds = new Set()" in response.data
    assert b"processedSignalIds.has(message.id)" in response.data
    assert b"Number(data.server_time) - 1" in response.data
    assert b"data.status === 'missed'" in response.data
    assert b"/ice-servers" in response.data
    assert b"await loadIceConfiguration()" in response.data
    assert response.data.index(b"await loadIceConfiguration()") < response.data.index(b"new RTCPeerConnection(rtcConfig)")
    assert b"cache: 'no-store'" in response.data
    assert b"peerConnection.getStats()" in response.data
    assert b"packetLossPercent >= 8" in response.data
    assert b"consecutivePoorSamples >= 2" in response.data
    assert b"consecutiveGoodSamples >= 4" in response.data
    assert b"sender.setParameters(parameters)" in response.data
    assert b"selectedLocalCandidate.candidateType === 'relay'" in response.data
    assert b"/quality" in response.data
    assert b"pendingLocalIceCandidates.push(event.candidate)" in response.data
    assert b"publishLocalDescription('offer', offer)" in response.data
    assert b"publishLocalDescription('answer', answer)" in response.data
    assert b"window.crypto.randomUUID" in response.data
    assert b"event_id: eventId" in response.data
    assert b"data.event_id === eventId" in response.data
    assert b"attempt < 3" in response.data
    assert b"signalingAckUrl" in response.data
    assert b"acknowledgeSignalDelivery(deliveryAcks)" in response.data
    assert b"processedSignalIds.has(message.id)" in response.data
    assert b"deliveryAcks.push(message.id)" in response.data


def test_call_page_keeps_caption_recognition_disabled_without_consent(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"live_call_captions": False})
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    response = client.get(f"/video_call/{alice.email}/{bob.email}")

    assert response.status_code == 200
    assert b"const captionsAllowed = false" in response.data
