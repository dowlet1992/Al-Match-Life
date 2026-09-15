import json

import pytest

from backend.ai_provider import OllamaProvider, get_ai_provider


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_default_ai_provider_is_local_ollama():
    provider = get_ai_provider({})
    assert provider.name == "ollama"
    assert provider.base_url == "http://127.0.0.1:11434"
    assert provider.model == "qwen2.5:7b"


def test_remote_ollama_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("ALLOW_REMOTE_AI_PROVIDER", raising=False)
    with pytest.raises(ValueError):
        OllamaProvider(base_url="https://ai.example.com")


def test_ollama_chat_uses_provider_contract(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse({"message": {"content": " Local answer "}})

    monkeypatch.setattr("backend.ai_provider.urllib.request.urlopen", fake_urlopen)
    provider = OllamaProvider(model="qwen-test", timeout=12)
    result = provider.chat([{"role": "user", "content": "Hello"}], max_tokens=50)

    assert result == "Local answer"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "qwen-test"
    assert captured["payload"]["options"]["num_predict"] == 50
    assert captured["payload"]["options"]["num_ctx"] == 4096
    assert captured["payload"]["options"]["repeat_penalty"] == 1.12
    assert captured["payload"]["keep_alive"] == "15m"
