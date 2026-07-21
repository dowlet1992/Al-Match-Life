from backend.auth_tokens import create_access_token, create_refresh_token, hash_token, verify_access_token, verify_refresh_token


def test_access_token_round_trip_normalizes_email():
    token = create_access_token("Alice@Example.com", "secret", issued_at=100, expires_in_seconds=60, session_version=3)

    payload = verify_access_token(token, "secret", now=120)

    assert payload["email"] == "alice@example.com"
    assert payload["issued_at"] == 100
    assert payload["expires_at"] == 160
    assert payload["session_version"] == 3


def test_access_token_rejects_wrong_secret():
    token = create_access_token("alice@example.com", "secret", issued_at=100, expires_in_seconds=60)

    assert verify_access_token(token, "other-secret", now=120) is None


def test_access_token_rejects_expired_token():
    token = create_access_token("alice@example.com", "secret", issued_at=100, expires_in_seconds=60)

    assert verify_access_token(token, "secret", now=161) is None


def test_access_token_rejects_malformed_token():
    assert verify_access_token("bad-token", "secret") is None


def test_refresh_token_round_trip_contains_rotation_identity():
    token = create_refresh_token(
        "Alice@Example.com", "secret", issued_at=100, expires_in_seconds=60,
        session_version=4, token_id="token-1", family_id="family-1",
    )

    payload = verify_refresh_token(token, "secret", now=120)

    assert payload == {
        "email": "alice@example.com", "token_id": "token-1", "family_id": "family-1",
        "session_version": 4, "issued_at": 100, "expires_at": 160,
    }


def test_refresh_token_rejects_expired_and_access_tokens():
    refresh = create_refresh_token("alice@example.com", "secret", issued_at=100, expires_in_seconds=60)
    access = create_access_token("alice@example.com", "secret", issued_at=100, expires_in_seconds=60)

    assert verify_refresh_token(refresh, "secret", now=161) is None
    assert verify_refresh_token(access, "secret", now=120) is None


def test_token_hash_is_deterministic_without_storing_raw_token():
    assert hash_token("refresh-secret") == hash_token("refresh-secret")
    assert hash_token("refresh-secret") != "refresh-secret"
