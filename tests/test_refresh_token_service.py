from backend.services.refresh_token_service import issue_refresh_token, revoke_refresh_token, rotate_refresh_token
from backend.repositories.refresh_session_repository import JsonRefreshSessionRepository


def test_refresh_token_rotates_once_and_preserves_family(tmp_path):
    repository = JsonRefreshSessionRepository(tmp_path / "sessions.json")
    issued = issue_refresh_token(
        "alice@example.com", "secret", 1, repository,
        device_id="iphone", expires_in_seconds=600, now=100,
    )

    rotated = rotate_refresh_token(
        issued["refresh_token"], "secret", 1, repository,
        expires_in_seconds=600, now=120,
    )

    assert rotated["ok"] is True
    assert rotated["family_id"] == issued["family_id"]
    assert rotated["refresh_token"] != issued["refresh_token"]


def test_refresh_token_reuse_revokes_entire_family(tmp_path):
    repository = JsonRefreshSessionRepository(tmp_path / "sessions.json")
    issued = issue_refresh_token("alice@example.com", "secret", 1, repository, now=100)
    first = rotate_refresh_token(issued["refresh_token"], "secret", 1, repository, now=120)

    reused = rotate_refresh_token(issued["refresh_token"], "secret", 1, repository, now=130)
    replacement_rejected = rotate_refresh_token(first["refresh_token"], "secret", 1, repository, now=140)

    assert reused == {"ok": False, "error": "refresh_token_reuse"}
    assert replacement_rejected == {"ok": False, "error": "refresh_token_reuse"}


def test_refresh_token_rejects_rotated_account_session(tmp_path):
    repository = JsonRefreshSessionRepository(tmp_path / "sessions.json")
    issued = issue_refresh_token("alice@example.com", "secret", 1, repository, now=100)

    result = rotate_refresh_token(issued["refresh_token"], "secret", 2, repository, now=120)

    assert result == {"ok": False, "error": "refresh_token_revoked"}


def test_refresh_token_revoke_invalidates_whole_family(tmp_path):
    repository = JsonRefreshSessionRepository(tmp_path / "refresh.json")
    issued = issue_refresh_token("alice@example.com", "secret", 1, repository)

    assert revoke_refresh_token(issued["refresh_token"], "secret", repository) is True
    assert rotate_refresh_token(
        issued["refresh_token"], "secret", 1, repository,
    ) == {"ok": False, "error": "refresh_token_reuse"}
