import json
import os
import secrets
import urllib.error
import urllib.request


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


def _multipart_body(fields, file_field, filename, content_type, audio_bytes):
    boundary = "----AIMatchLife" + secrets.token_hex(16)
    chunks = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            str(value).encode("utf-8"), b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        audio_bytes, b"\r\n", f"--{boundary}--\r\n".encode(),
    ])
    return boundary, b"".join(chunks)


def transcribe_audio_chunk(audio_bytes, content_type, language="", environ=None, urlopen=None):
    metadata, validation_error = validate_audio_chunk(audio_bytes, content_type)
    if validation_error:
        return {"ok": False, "error": validation_error}
    environ = os.environ if environ is None else environ
    api_key = str(environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        return {"ok": False, "error": "transcription_provider_unavailable"}
    model = str(environ.get("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")).strip()
    fields = {"model": model, "response_format": "json"}
    if language and language != "unknown":
        fields["language"] = language
    boundary, body = _multipart_body(
        fields, "file", metadata["filename"], metadata["content_type"], audio_bytes,
    )
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        opener = urlopen or urllib.request.urlopen
        with opener(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        text = str(payload.get("text", "")).strip() if isinstance(payload, dict) else ""
        detected_language = str(payload.get("language", "")).strip().lower() if isinstance(payload, dict) else ""
        return {"ok": True, "text": text, "model": model, "detected_language": detected_language} if text else {"ok": False, "error": "empty_transcription"}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError):
        return {"ok": False, "error": "transcription_provider_failed"}
