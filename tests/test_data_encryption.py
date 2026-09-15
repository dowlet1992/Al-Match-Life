import json

import pytest
from cryptography.fernet import Fernet

from backend.data_encryption import DataEncryptionError, ENCRYPTED_FILE_PREFIX
from backend.repositories.json_store import JsonStore


def test_json_store_encrypts_and_authenticates_data_when_key_is_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    path = tmp_path / "sensitive.json"
    store = JsonStore(path, {})

    store.save({"email": "alice@example.com", "token": "private"})

    raw = path.read_bytes()
    assert raw.startswith(ENCRYPTED_FILE_PREFIX)
    assert b"alice@example.com" not in raw
    assert store.load() == {"email": "alice@example.com", "token": "private"}


def test_json_store_reads_plaintext_then_encrypts_on_next_save(tmp_path, monkeypatch):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"legacy": True}), encoding="utf-8")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    store = JsonStore(path, {})

    data = store.load()
    store.save(data)

    assert path.read_bytes().startswith(ENCRYPTED_FILE_PREFIX)


def test_encrypted_json_requires_the_configured_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    path = tmp_path / "sensitive.json"
    store = JsonStore(path, {})
    store.save({"secret": True})
    JsonStore.clear_cache()
    monkeypatch.delenv("DATA_ENCRYPTION_KEY")

    with pytest.raises(DataEncryptionError):
        store.load()
