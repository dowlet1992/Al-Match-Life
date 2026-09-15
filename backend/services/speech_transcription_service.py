import os

from backend.speech_provider import get_speech_provider, speech_provider_status


MAX_AUDIO_CHUNK_BYTES = 2 * 1024 * 1024
MAX_TRANSCRIPTION_REQUEST_BYTES = MAX_AUDIO_CHUNK_BYTES + 64 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/webm": "chunk.webm",
    "audio/ogg": "chunk.ogg",
    "audio/wav": "chunk.wav",
    "audio/x-wav": "chunk.wav",
    "audio/mpeg": "chunk.mp3",
    "audio/mp4": "chunk.m4a",
}


def audio_signature_matches(audio_bytes, content_type):
    content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "audio/webm":
        return audio_bytes.startswith(b"\x1a\x45\xdf\xa3")
    if content_type == "audio/ogg":
        return audio_bytes.startswith(b"OggS")
    if content_type in {"audio/wav", "audio/x-wav"}:
        return len(audio_bytes) >= 12 and audio_bytes.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE"
    if content_type == "audio/mp4":
        return len(audio_bytes) >= 12 and audio_bytes[4:8] == b"ftyp"
    if content_type == "audio/mpeg":
        return audio_bytes.startswith(b"ID3") or (len(audio_bytes) >= 2 and audio_bytes[0] == 0xFF and audio_bytes[1] & 0xE0 == 0xE0)
    return False


def validate_audio_chunk(audio_bytes, content_type):
    content_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        return None, "unsupported_audio_type"
    if not audio_bytes:
        return None, "empty_audio_chunk"
    if len(audio_bytes) > MAX_AUDIO_CHUNK_BYTES:
        return None, "audio_chunk_too_large"
    if not audio_signature_matches(audio_bytes, content_type):
        return None, "invalid_audio_signature"
    return {"content_type": content_type, "filename": ALLOWED_AUDIO_TYPES[content_type]}, ""


def provider_available(environ=None):
    return bool(speech_provider_status(environ).get("enabled"))


def transcribe_audio_chunk(audio_bytes, content_type, language="", environ=None, urlopen=None, provider=None):
    metadata, validation_error = validate_audio_chunk(audio_bytes, content_type)
    if validation_error:
        return {"ok": False, "error": validation_error}
    environ = os.environ if environ is None else environ
    try:
        provider = provider or get_speech_provider(environ, urlopen=urlopen)
    except (TypeError, ValueError):
        return {"ok": False, "error": "transcription_provider_unavailable"}
    if not provider.is_available():
        return {"ok": False, "error": "transcription_provider_unavailable"}
    try:
        return provider.transcribe(audio_bytes, metadata["filename"], metadata["content_type"], language)
    except (OSError, RuntimeError, TypeError, ValueError):
        return {"ok": False, "error": "transcription_provider_failed"}
