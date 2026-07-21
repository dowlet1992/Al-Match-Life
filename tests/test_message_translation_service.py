from backend.services import message_translation_service


def normalize(value):
    value = str(value or "").lower()
    return value if value in {"en", "de", "ru"} else "unknown"


def test_translation_is_cached_after_first_provider_call():
    message = {"message": "Hello", "source_language": "en", "translations": {}}
    calls = []

    first = message_translation_service.translate_message(
        message, "de", normalize, lambda text, source, target: calls.append((text, source, target)) or "Hallo",
    )
    second = message_translation_service.translate_message(
        message, "de", normalize, lambda *args: "should not run",
    )

    assert first["translated_text"] == "Hallo"
    assert first["cached"] is False
    assert second["cached"] is True
    assert calls == [("Hello", "en", "de")]


def test_translation_rejects_unknown_target_language():
    result = message_translation_service.translate_message(
        {"message": "Hello", "source_language": "en"}, "xx", normalize, lambda *args: "",
    )

    assert result == {"ok": False, "error": "unsupported_target_language"}


def test_auto_translation_only_processes_latest_incoming_messages():
    messages = [
        {"id": 1, "from": "bob@example.com", "to": "alice@example.com", "message": "Hallo", "source_language": "de"},
        {"id": 2, "from": "alice@example.com", "to": "bob@example.com", "message": "Danke", "source_language": "de"},
    ]

    result = message_translation_service.auto_translate_incoming(
        messages, "alice@example.com", "en", normalize, lambda *args: "Hello", limit=20,
    )

    assert result["changed"] == 1
    assert messages[0]["translations"] == {"en": "Hello"}
    assert "translations" not in messages[1]
