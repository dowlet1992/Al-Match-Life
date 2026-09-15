from backend.speech_provider import FasterWhisperProvider, get_speech_provider, speech_provider_status


def test_local_whisper_is_the_default_speech_provider(monkeypatch):
    monkeypatch.setattr("backend.speech_provider.importlib.util.find_spec", lambda name: None)

    provider = get_speech_provider({})

    assert isinstance(provider, FasterWhisperProvider)
    assert provider.name == "faster-whisper"
    assert provider.model_name == "base"
    assert speech_provider_status({}) == {"enabled": False, "provider": "faster-whisper"}


def test_unknown_speech_provider_fails_closed():
    assert speech_provider_status({"SPEECH_PROVIDER": "unknown"}) == {
        "enabled": False,
        "provider": "invalid",
    }
