import json

from backend.services import feed_translation_service


def deps(events=None):
    events = events if events is not None else []
    return {
        "clean_text": lambda value: str(value or "").strip(),
        "content_languages": lambda: {"en": "English", "ru": "Русский", "unknown": "Unknown"},
        "current_session_email": lambda: "alice@example.com",
        "log_security_event": lambda event_type, email="", details="": events.append((event_type, email, details)),
        "normalize_content_language_code": lambda value: value if value in {"en", "ru"} else "unknown",
    }


def test_generate_ai_translation_summary_returns_empty_text_message(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = feed_translation_service.generate_ai_translation_summary("", "en", "ru", deps())

    assert result == "Текст для перевода не найден."


def test_generate_ai_translation_summary_returns_fallback_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = feed_translation_service.generate_ai_translation_summary("Hello", "en", "ru", deps())

    assert "OPENAI_API_KEY не подключён" in result
    assert "English" in result
    assert "Русский" in result


def test_generate_ai_translation_summary_uses_openai_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps({
                "choices": [
                    {"message": {"content": "Translation:\nПривет\n\nShort summary:\nGreeting"}}
                ]
            }).encode("utf-8")

    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["timeout"] = timeout
        captured["auth"] = request.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(feed_translation_service.urllib.request, "urlopen", fake_urlopen)

    result = feed_translation_service.generate_ai_translation_summary("Hello", "en", "ru", deps())

    assert "Привет" in result
    assert captured["timeout"] == 25
    assert captured["auth"] == "Bearer sk-test"
