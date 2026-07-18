import pytest

from backend.database import (
    DatabaseSettings,
    PostgresClient,
    load_database_settings,
    mask_database_url,
    validate_database_settings,
)


def test_load_database_settings_defaults_to_json():
    settings = load_database_settings({})

    assert settings.storage_backend == "json"
    assert settings.database_url == ""
    assert settings.postgres_enabled is False


def test_load_database_settings_reads_postgres_config():
    settings = load_database_settings({
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:secret@example.com/db",
        "DATABASE_CONNECT_TIMEOUT": "20",
    })

    assert settings.storage_backend == "postgres"
    assert settings.ready_for_postgres is True
    assert settings.connect_timeout_seconds == 20


def test_mask_database_url_hides_passwords_and_tokens():
    masked = mask_database_url(
        "postgresql://user:secret@example.com/db?sslmode=require&token=abc"
    )

    assert "secret" not in masked
    assert "abc" not in masked
    assert "user:***@example.com" in masked
    assert "token=%2A%2A%2A" in masked


def test_validate_database_settings_requires_url_for_postgres():
    issues = validate_database_settings(DatabaseSettings(storage_backend="postgres"))

    assert "DATABASE_URL is required" in issues[0]


def test_validate_database_settings_rejects_non_postgres_url():
    issues = validate_database_settings(DatabaseSettings(
        storage_backend="postgres",
        database_url="mysql://example",
    ))

    assert "DATABASE_URL must start" in issues[0]


def test_postgres_client_requires_valid_settings():
    client = PostgresClient(DatabaseSettings(storage_backend="postgres"))

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        client.connect()
