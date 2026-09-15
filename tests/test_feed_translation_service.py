from backend.services import feed_translation_service


def deps(events=None, available=False, chat=None):
    events = events if events is not None else []
    return {
        "clean_text": lambda value: str(value or "").strip(),
        "content_languages": lambda: {"en": "English", "ru": "Русский", "unknown": "Unknown"},
        "current_session_email": lambda: "alice@example.com",
        "provider_available": lambda: available,
        "chat": chat or (lambda *args, **kwargs: ""),
        "log_security_event": lambda event_type, email="", details="": events.append((event_type, email, details)),
        "normalize_content_language_code": lambda value: value if value in {"en", "ru"} else "unknown",
    }


def test_generate_ai_translation_summary_returns_empty_text_message():
    result = feed_translation_service.generate_ai_translation_summary("", "en", "ru", deps())

    assert result == "Текст для перевода не найден."


def test_generate_ai_translation_summary_returns_fallback_without_local_provider():
    result = feed_translation_service.generate_ai_translation_summary("Hello", "en", "ru", deps())

    assert "локальная AI-модель не подключена" in result
    assert "English" in result
    assert "Русский" in result


def test_generate_ai_translation_summary_uses_configured_provider():
    captured = {}

    def fake_chat(messages, **options):
        captured["messages"] = messages
        captured["options"] = options
        return "Translation:\nПривет\n\nShort summary:\nGreeting"

    result = feed_translation_service.generate_ai_translation_summary(
        "Hello", "en", "ru", deps(available=True, chat=fake_chat)
    )

    assert "Привет" in result
    assert captured["options"] == {"temperature": 0.2, "max_tokens": 700, "strict": True}
    assert "Hello" in captured["messages"][1]["content"]
