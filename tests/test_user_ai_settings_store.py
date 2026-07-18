from backend import user_ai_settings_store
from backend.repositories.user_ai_settings_repository import JsonUserAiSettingsRepository


def test_user_ai_settings_store_loads_empty_settings(monkeypatch, tmp_path):
    repository = JsonUserAiSettingsRepository(tmp_path / "user_ai_settings.json", tmp_path / "privacy_data.json")
    monkeypatch.setattr(user_ai_settings_store, "get_user_ai_settings_repository", lambda: repository)

    assert user_ai_settings_store.load_user_ai_settings("user@example.com") == {}


def test_user_ai_settings_store_reads_legacy_settings(monkeypatch, tmp_path):
    repository = JsonUserAiSettingsRepository(tmp_path / "user_ai_settings.json", tmp_path / "privacy_data.json")
    repository.legacy_privacy_store.save({"user@example.com": {"ai_recommendations": False}})
    monkeypatch.setattr(user_ai_settings_store, "get_user_ai_settings_repository", lambda: repository)

    assert user_ai_settings_store.load_user_ai_settings("USER@example.com") == {
        "ai_recommendations": False
    }


def test_user_ai_settings_store_prefers_new_settings(monkeypatch, tmp_path):
    repository = JsonUserAiSettingsRepository(tmp_path / "user_ai_settings.json", tmp_path / "privacy_data.json")
    repository.settings_store.save({"user@example.com": {"ai_recommendations": True}})
    repository.legacy_privacy_store.save({"user@example.com": {"ai_recommendations": False}})
    monkeypatch.setattr(user_ai_settings_store, "get_user_ai_settings_repository", lambda: repository)

    assert user_ai_settings_store.load_user_ai_settings("user@example.com") == {
        "ai_recommendations": True
    }


def test_user_ai_settings_store_saves_settings(monkeypatch, tmp_path):
    repository = JsonUserAiSettingsRepository(tmp_path / "user_ai_settings.json", tmp_path / "privacy_data.json")
    monkeypatch.setattr(user_ai_settings_store, "get_user_ai_settings_repository", lambda: repository)

    user_ai_settings_store.save_user_ai_settings("USER@example.com", {"private_profile": True})

    assert user_ai_settings_store.load_user_ai_settings("user@example.com") == {
        "private_profile": True
    }
