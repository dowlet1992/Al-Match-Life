from backend.database import DatabaseSettings
from backend.repositories.refresh_session_repository import (
    JsonRefreshSessionRepository,
    PostgresRefreshSessionRepository,
    get_refresh_session_repository,
)


def session_payload(token_id="token-1", family_id="family-1"):
    return {
        "token_id": token_id, "family_id": family_id, "email": "alice@example.com",
        "token_hash": "hash", "device_id": "device", "session_version": 1,
        "issued_at": 100, "expires_at": 200,
    }


def test_json_refresh_session_rotation_and_reuse_detection(tmp_path):
    repository = JsonRefreshSessionRepository(tmp_path / "refresh.json")
    repository.create(session_payload())

    assert repository.get("token-1")["token_hash"] == "hash"
    assert repository.mark_rotated("token-1", "token-2") is True
    assert repository.mark_rotated("token-1", "token-3") is False
    assert repository.get("token-1")["replaced_by_token_id"] == "token-2"


def test_json_refresh_session_can_revoke_whole_family(tmp_path):
    repository = JsonRefreshSessionRepository(tmp_path / "refresh.json")
    repository.create(session_payload("token-1"))
    repository.create(session_payload("token-2"))

    assert repository.revoke_family("family-1") is True
    assert repository.get("token-1")["revoked_at"]
    assert repository.get("token-2")["revoked_at"]


def test_refresh_repository_selects_postgres_backend():
    repository = get_refresh_session_repository(
        settings=DatabaseSettings(storage_backend="postgres", database_url="postgresql://example/db"),
        client=object(),
    )
    assert isinstance(repository, PostgresRefreshSessionRepository)
