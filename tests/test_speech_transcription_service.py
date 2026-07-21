import json

from backend.services import speech_transcription_service


WEBM_AUDIO = b"\x1a\x45\xdf\xa3valid-audio"


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"text": "Hello from audio", "language": "en"}).encode()


def test_transcription_uses_bounded_multipart_request():
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    result = speech_transcription_service.transcribe_audio_chunk(
        WEBM_AUDIO, "audio/webm", "en",
        environ={"OPENAI_API_KEY": "sk-test"}, urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["text"] == "Hello from audio"
    assert result["detected_language"] == "en"
    assert captured["request"].full_url.endswith("/v1/audio/transcriptions")
    assert b'gpt-4o-mini-transcribe' in captured["request"].data
    assert b'name="file"; filename="chunk.webm"' in captured["request"].data


def test_transcription_rejects_unsupported_or_oversized_audio():
    unsupported = speech_transcription_service.transcribe_audio_chunk(
        b"audio", "application/octet-stream", environ={"OPENAI_API_KEY": "sk-test"},
    )
    oversized = speech_transcription_service.transcribe_audio_chunk(
        b"x" * (speech_transcription_service.MAX_AUDIO_CHUNK_BYTES + 1),
        "audio/webm", environ={"OPENAI_API_KEY": "sk-test"},
    )

    assert unsupported == {"ok": False, "error": "unsupported_audio_type"}
    assert oversized == {"ok": False, "error": "audio_chunk_too_large"}


def test_transcription_fails_closed_without_provider_key():
    result = speech_transcription_service.transcribe_audio_chunk(WEBM_AUDIO, "audio/webm", environ={})

    assert result == {"ok": False, "error": "transcription_provider_unavailable"}


def test_transcription_rejects_spoofed_audio_mime_type():
    result = speech_transcription_service.transcribe_audio_chunk(
        b"not-really-webm", "audio/webm", environ={"OPENAI_API_KEY": "sk-test"},
    )

    assert result == {"ok": False, "error": "invalid_audio_signature"}
