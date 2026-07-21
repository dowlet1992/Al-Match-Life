import json
import os
import urllib.error
import urllib.request


REALTIME_ENDPOINT = "https://api.openai.com/v1/realtime/client_secrets"
REALTIME_CALLS_ENDPOINT = "https://api.openai.com/v1/realtime/calls"
SPEECH_ENDPOINT = "https://api.openai.com/v1/audio/speech"
BUILT_IN_VOICES = {
    "alloy", "ash", "ballad", "coral", "echo", "fable", "onyx",
    "nova", "sage", "shimmer", "verse", "marin", "cedar",
}
MAX_SPEECH_TEXT_CHARS = 1200
MAX_SPEECH_RESPONSE_BYTES = 4 * 1024 * 1024


def provider_available(environ=None):
    environ = os.environ if environ is None else environ
    return bool(str(environ.get("OPENAI_API_KEY", "")).strip())


def _post_json(url, payload, api_key, timeout, urlopen=None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urlopen or urllib.request.urlopen
    return opener(request, timeout=timeout)


def create_transcription_session(language="", environ=None, urlopen=None):
    """Mint a one-minute client credential; never return the permanent API key."""
    environ = os.environ if environ is None else environ
    api_key = str(environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return {"ok": False, "error": "realtime_provider_unavailable"}
    model = str(environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime")).strip()
    transcription_model = str(
        environ.get("OPENAI_REALTIME_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
    ).strip()
    transcription = {"model": transcription_model}
    language = str(language or "").strip().lower()
    if language and language not in {"auto", "unknown"}:
        transcription["language"] = language
    payload = {"session": {
        "type": "realtime",
        "model": model,
        "output_modalities": ["text"],
        "audio": {"input": {
            "transcription": transcription,
            "noise_reduction": {"type": "near_field"},
            "turn_detection": {
                "type": "server_vad", "threshold": 0.5,
                "prefix_padding_ms": 300, "silence_duration_ms": 350,
                "create_response": False, "interrupt_response": False,
            },
        }},
    }}
    try:
        with _post_json(REALTIME_ENDPOINT, payload, api_key, 12, urlopen) as response:
            result = json.loads(response.read().decode("utf-8"))
        secret = result.get("client_secret", {}) if isinstance(result, dict) else {}
        value = str(secret.get("value", "")).strip() if isinstance(secret, dict) else ""
        expires_at = secret.get("expires_at") if isinstance(secret, dict) else None
        if not value or not isinstance(expires_at, (int, float)):
            return {"ok": False, "error": "invalid_realtime_provider_response"}
        return {
            "ok": True,
            "client_secret": value,
            "expires_at": int(expires_at),
            "model": model,
            "transcription_model": transcription_model,
            "transport": "webrtc",
            "calls_endpoint": REALTIME_CALLS_ENDPOINT,
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError, OSError):
        return {"ok": False, "error": "realtime_provider_failed"}


def synthesize_speech(text, voice="coral", environ=None, urlopen=None):
    environ = os.environ if environ is None else environ
    api_key = str(environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return {"ok": False, "error": "speech_provider_unavailable"}
    text = str(text or "").strip()
    voice = str(voice or "coral").strip().lower()
    if not text:
        return {"ok": False, "error": "empty_speech_text"}
    if len(text) > MAX_SPEECH_TEXT_CHARS:
        return {"ok": False, "error": "speech_text_too_long"}
    if voice not in BUILT_IN_VOICES:
        return {"ok": False, "error": "unsupported_speech_voice"}
    model = str(environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")).strip()
    payload = {"model": model, "voice": voice, "input": text, "response_format": "mp3"}
    try:
        with _post_json(SPEECH_ENDPOINT, payload, api_key, 25, urlopen) as response:
            audio = response.read(MAX_SPEECH_RESPONSE_BYTES + 1)
        if not audio or len(audio) > MAX_SPEECH_RESPONSE_BYTES:
            return {"ok": False, "error": "invalid_speech_provider_response"}
        return {"ok": True, "audio": audio, "content_type": "audio/mpeg", "model": model, "voice": voice}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError):
        return {"ok": False, "error": "speech_provider_failed"}
