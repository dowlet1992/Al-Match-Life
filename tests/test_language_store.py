from backend import language
from backend.repositories import JsonStore


def test_language_store_falls_back_to_default_dict(monkeypatch, tmp_path):
    store = JsonStore(tmp_path / "language_data.json", {})
    store.save([])
    monkeypatch.setattr(language, "_language_store", store)

    assert language.load_languages() == {"ru": {}}


def test_get_translations_uses_default_language(monkeypatch, tmp_path):
    store = JsonStore(tmp_path / "language_data.json", {})
    store.save({"ru": {"hello": "Привет"}, "en": {"hello": "Hello"}})
    monkeypatch.setattr(language, "_language_store", store)

    assert language.get_translations("unknown") == {"hello": "Привет"}
    assert language.get_translations("en-US") == {"hello": "Hello"}
