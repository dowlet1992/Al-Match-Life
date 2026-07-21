import io
import json

from backend.services import realtime_speech_service as service


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


def test_realtime_session_uses_permanent_key_only_server_side():
    captured = {}

    def open_request(request, timeout):
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.data)
        return FakeResponse(json.dumps({
            "client_secret": {"value": "ek_short_lived", "expires_at": 1900000000},
        }).encode())

    result = service.create_transcription_session(
        "de", environ={"OPENAI_API_KEY": "sk-permanent"}, urlopen=open_request,
    )

    assert result["ok"] is True
    assert result["client_secret"] == "ek_short_lived"
    assert "sk-permanent" not in str(result)
    assert captured["authorization"] == "Bearer sk-permanent"
    session = captured["payload"]["session"]
    assert session["type"] == "realtime"
    assert session["output_modalities"] == ["text"]
    assert session["audio"]["input"]["transcription"]["language"] == "de"
    assert session["audio"]["input"]["turn_detection"]["create_response"] is False
    assert result["calls_endpoint"] == "https://api.openai.com/v1/realtime/calls"


def test_realtime_session_fails_closed_without_provider_key():
    assert service.create_transcription_session(environ={}) == {
        "ok": False, "error": "realtime_provider_unavailable",
    }


def test_speech_rejects_custom_voice_before_provider_call():
    calls = []
    result = service.synthesize_speech(
        "hello", "voice_custom", environ={"OPENAI_API_KEY": "sk-test"},
        urlopen=lambda *args: calls.append(args),
    )
    assert result == {"ok": False, "error": "unsupported_speech_voice"}
    assert calls == []


def test_speech_returns_bounded_mp3_bytes():
    result = service.synthesize_speech(
        "Hallo", "coral", environ={"OPENAI_API_KEY": "sk-test"},
        urlopen=lambda request, timeout: FakeResponse(b"ID3audio"),
    )
    assert result["ok"] is True
    assert result["audio"] == b"ID3audio"
    assert result["content_type"] == "audio/mpeg"
