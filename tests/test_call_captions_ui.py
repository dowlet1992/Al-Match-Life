from pathlib import Path

import app
from backend.models import User


CALL_JS = Path("static/call.js").read_bytes()


def rendered_assets(response):
    return response.data + CALL_JS


def test_call_page_renders_opt_in_caption_controls(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {
        "live_call_captions": True, "allow_server_call_transcription": True,
        "allow_ai_voice_translation": True,
        "call_voice_translation_enabled": True,
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
    assert b'id="captionsBtn"' in rendered_assets(response)
    assert b'id="captionPanel"' in rendered_assets(response)
    assert b'id="captionTranslationRow"' in rendered_assets(response)
    assert b'id="captionTranslationText"' in rendered_assets(response)
    assert b'id="captionState"' in rendered_assets(response)
    assert b'data-captions-allowed="true"' in rendered_assets(response)
    assert b"window.SpeechRecognition || window.webkitSpeechRecognition" in rendered_assets(response)
    assert b'data-recognition-language="de"' in rendered_assets(response)
    assert b"/api/calls/" in rendered_assets(response)
    assert b'data-auto-translate-captions="true"' in rendered_assets(response)
    assert b'data-server-transcription-allowed="true"' in rendered_assets(response)
    assert b'data-realtime-transcription-available="false"' in rendered_assets(response)
    assert b'data-ai-voice-translation-allowed="true"' in rendered_assets(response)
    assert b'data-voice-translation-enabled="true"' in rendered_assets(response)
    assert b'/translation/preferences' in rendered_assets(response)
    assert b'voice_translation: aiVoiceTranslationEnabled' in rendered_assets(response)
    assert b'/static/realtime-caption-client.js' in rendered_assets(response)
    assert b'/static/call.js' in rendered_assets(response)
    assert b'/static/call.css' in rendered_assets(response)
    assert b"<style>" not in rendered_assets(response)
    assert b"<script>" not in response.data
    assert b" onload=" not in rendered_assets(response)
    assert b" onclick=" not in rendered_assets(response)
    assert b'data-call-action="mute"' in rendered_assets(response)
    assert b'id="translationPanel"' in rendered_assets(response)
    assert b'id="callSourceLanguage"' in rendered_assets(response)
    assert b'id="callTargetLanguage"' in rendered_assets(response)
    assert b'value="it"' in rendered_assets(response)
    assert b'value="af"' in rendered_assets(response)
    assert b'value="ur"' in rendered_assets(response)
    assert b'value="vi"' in rendered_assets(response)
    assert b'data-call-action="translation-settings"' in rendered_assets(response)
    assert b'data-call-action="group-call"' not in rendered_assets(response)
    assert b'id="callMoreBtn"' in rendered_assets(response)
    assert b'id="addParticipantMenuBtn"' in rendered_assets(response)
    assert b'id="participantPicker"' in rendered_assets(response)
    assert b'/api/conferences/eligible' in rendered_assets(response)
    controls = response.data.split(b'<div class="controls">', 1)[1].split(b'</div>', 1)[0]
    more_menu = response.data.split(b'<div class="call-more-menu"', 1)[1].split(b'</div>', 1)[0]
    assert b'id="muteBtn"' in controls
    assert b'id="speakerBtn"' in controls
    assert b'id="captionsBtn"' not in controls
    assert b'id="translationSettingsBtn"' not in controls
    assert b'id="captionsBtn"' in more_menu
    assert b'id="translationSettingsBtn"' in more_menu
    video_response = client.get(f"/video_call/{alice.email}/{bob.email}")
    video_controls = video_response.data.split(b'<div class="controls">', 1)[1].split(b'</div>', 1)[0]
    video_more_menu = video_response.data.split(b'<div class="call-more-menu"', 1)[1].split(b'</div>', 1)[0]
    assert b'id="muteBtn"' in video_controls
    assert b'id="cameraBtn"' in video_controls
    assert b'id="speakerBtn"' not in video_controls
    assert b'id="flipBtn"' not in video_controls
    assert b'id="flipBtn"' in video_more_menu
    assert b'id="screenShareBtn"' in video_more_menu
    assert b'data-call-action="screen-share"' in video_more_menu
    assert b'aria-pressed="false"' in video_more_menu
    assert b"navigator.mediaDevices.getDisplayMedia" in rendered_assets(response)
    assert b"await sender.replaceTrack(displayTrack)" in rendered_assets(response)
    assert b"displayTrack.onended = function() { stopScreenShare(); }" in rendered_assets(response)
    assert b"await sender.replaceTrack(cameraTrack)" in rendered_assets(response)
    assert b"displayTrack.contentHint = 'detail'" in rendered_assets(response)
    assert b"sendSignal('conference_upgrade'" in rendered_assets(response)
    assert b"novix-call-translation" in rendered_assets(response)
    assert b"target_language: captionTargetLanguage" in rendered_assets(response)
    assert b"showTranslatedCaption(receiverName, caption.text || '', translatedText)" in rendered_assets(response)
    assert b"}, 2500)" in rendered_assets(response)
    assert b"button.addEventListener('click'" in rendered_assets(response)
    assert b"startRealtimeCaptions" in rendered_assets(response)
    assert b"enqueueTranslatedSpeech" in rendered_assets(response)
    assert b"SpeechSynthesisUtterance" in rendered_assets(response)
    assert b"speakOnDevice" in rendered_assets(response)
    assert b"X-AI-Generated-Voice" in rendered_assets(response)
    assert b"remoteMedia.volume = Math.min(previousVolume, 0.28)" in rendered_assets(response)
    assert b"stopTranslatedSpeech()" in rendered_assets(response)
    assert b"translateRemoteCaption" in rendered_assets(response)
    assert b"startServerCaptionCycle" in rendered_assets(response)
    assert b"MediaRecorder" in rendered_assets(response)
    assert b"/transcribe" in rendered_assets(response)
    assert b"response.headers.get('Retry-After')" in rendered_assets(response)
    assert b"serverCaptionFailures >= 3" in rendered_assets(response)
    assert b"const maxReconnectAttempts = 3" in rendered_assets(response)
    assert b"createOffer({iceRestart: true})" in rendered_assets(response)
    assert b"peerConnection.restartIce" in rendered_assets(response)
    assert b"scheduleReconnect(5000)" in rendered_assets(response)
    assert b"reason: 'connection_lost'" in rendered_assets(response)
    assert b"window.addEventListener('offline'" in rendered_assets(response)
    assert b"window.addEventListener('online'" in rendered_assets(response)
    assert b"const processedSignalIds = new Set()" in rendered_assets(response)
    assert b"processedSignalIds.has(message.id)" in rendered_assets(response)
    assert b"Number(data.server_time) - 1" in rendered_assets(response)
    assert b"data.status === 'missed'" in rendered_assets(response)
    assert b"/ice-servers" in rendered_assets(response)
    assert b"await loadIceConfiguration()" in rendered_assets(response)
    assert rendered_assets(response).index(b"await loadIceConfiguration()") < rendered_assets(response).index(b"new RTCPeerConnection(rtcConfig)")
    assert b"cache: 'no-store'" in rendered_assets(response)
    assert b"peerConnection.getStats()" in rendered_assets(response)
    assert b'id="callQuality"' in rendered_assets(response)
    assert b"echoCancellation: true" in rendered_assets(response)
    assert b"noiseSuppression: true" in rendered_assets(response)
    assert b"autoGainControl: true" in rendered_assets(response)
    assert b"track.contentHint = 'speech'" in rendered_assets(response)
    assert b"parameters.encodings[0].networkPriority = 'high'" in rendered_assets(response)
    assert b"await prioritizeSpeechAudio()" in rendered_assets(response)
    assert b"audio: false, video: videoConstraints()" in rendered_assets(response)
    assert b"updateQualityIndicator(qualityLevel)" in rendered_assets(response)
    assert b"packetLossPercent >= 8" in rendered_assets(response)
    assert b"consecutivePoorSamples >= 2" in rendered_assets(response)
    assert b"consecutiveGoodSamples >= 4" in rendered_assets(response)
    assert b"sender.setParameters(parameters)" in rendered_assets(response)
    assert b"selectedLocalCandidate.candidateType === 'relay'" in rendered_assets(response)
    assert b"/quality" in rendered_assets(response)
    assert b"pendingLocalIceCandidates.push(event.candidate)" in rendered_assets(response)
    assert b"publishLocalDescription('offer', offer)" in rendered_assets(response)
    assert b"publishLocalDescription('answer', answer)" in rendered_assets(response)
    assert b"window.crypto.randomUUID" in rendered_assets(response)
    assert b"event_id: eventId" in rendered_assets(response)
    assert b"data.event_id === eventId" in rendered_assets(response)
    assert b"attempt < 3" in rendered_assets(response)
    assert b"signalingAckUrl" in rendered_assets(response)
    assert b"acknowledgeSignalDelivery(deliveryAcks)" in rendered_assets(response)
    assert b"processedSignalIds.has(message.id)" in rendered_assets(response)
    assert b"deliveryAcks.push(message.id)" in rendered_assets(response)


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
    assert b'data-captions-allowed="false"' in rendered_assets(response)
    assert b"window.location.href = '/settings/'" not in rendered_assets(response)
    assert b'captions_disabled_help' in response.data
    assert "Субтитры выключены в настройках".encode("utf-8") not in CALL_JS


def test_call_runtime_messages_use_the_active_locale_bundle():
    assert b"JSON.parse(callConfig.i18n" in CALL_JS
    assert b"t('call_in_progress'" in CALL_JS
    assert "Идёт звонок".encode("utf-8") not in CALL_JS
    assert "Соединение прервано".encode("utf-8") not in CALL_JS


def test_call_configuration_escapes_attribute_values(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User('Bob" onmouseover="alert(1)', 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {})
    monkeypatch.setattr(app, "get_avatar_url", lambda email: "/avatar.png")
    monkeypatch.setattr(app, "is_blocked", lambda one, two: False)
    monkeypatch.setattr(app, "is_restricted", lambda one, two: False)

    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email

    response = client.get(f"/audio_call/{alice.email}/{bob.email}")

    assert response.status_code == 200
    assert b'data-receiver-name="Bob" onmouseover=' not in response.data
    assert b'data-receiver-name="Bob&#34; onmouseover=&#34;alert(1)"' in response.data
