import app
from backend.i18n import LANGUAGE_CATALOG


class TranslationProvider:
    def __init__(self, calls):
        self.calls = calls

    def chat(self, messages, **options):
        self.calls.append((messages, options))
        return "Buongiorno"


def test_translation_uses_dedicated_low_latency_model(monkeypatch):
    environments = []
    calls = []
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": True})
    monkeypatch.setattr(app, "get_ai_provider", lambda environ=None: environments.append(environ) or TranslationProvider(calls))
    monkeypatch.setenv("OLLAMA_TRANSLATION_MODEL", "translation-fast")

    result = app.translate_message_text("Доброе утро", "ru", "it")

    assert result == "Buongiorno"
    assert environments[0]["OLLAMA_MODEL"] == "translation-fast"
    assert calls[0][1]["temperature"] == 0.05
    assert calls[0][1]["max_tokens"] == 600


def test_translation_accepts_every_language_in_the_shared_catalog(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": True})
    monkeypatch.setattr(app, "get_ai_provider", lambda environ=None: TranslationProvider(calls))

    for target in LANGUAGE_CATALOG:
        source = "en" if target != "en" else "de"
        assert app.translate_message_text("NOVIX 42 @user https://novix.test", source, target) == "Buongiorno"

    assert len(calls) == len(LANGUAGE_CATALOG)
    assert all("Return only the translated message" in messages[0]["content"] for messages, _ in calls)


def test_translation_skips_provider_when_languages_are_equal(monkeypatch):
    monkeypatch.setattr(app, "get_ai_provider_status", lambda: {"enabled": True})
    monkeypatch.setattr(app, "get_ai_provider", lambda environ=None: (_ for _ in ()).throw(AssertionError("provider must not run")))

    assert app.translate_message_text("Привет 👋", "ru", "ru") == "Привет 👋"
