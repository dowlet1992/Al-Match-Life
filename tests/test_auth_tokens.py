from backend.auth_tokens import create_access_token, verify_access_token


def test_access_token_round_trip_normalizes_email():
    token = create_access_token("Alice@Example.com", "secret", issued_at=100, expires_in_seconds=60)

    payload = verify_access_token(token, "secret", now=120)

    assert payload["email"] == "alice@example.com"
    assert payload["issued_at"] == 100
    assert payload["expires_at"] == 160


def test_access_token_rejects_wrong_secret():
    token = create_access_token("alice@example.com", "secret", issued_at=100, expires_in_seconds=60)

    assert verify_access_token(token, "other-secret", now=120) is None


def test_access_token_rejects_expired_token():
    token = create_access_token("alice@example.com", "secret", issued_at=100, expires_in_seconds=60)

    assert verify_access_token(token, "secret", now=161) is None


def test_access_token_rejects_malformed_token():
    assert verify_access_token("bad-token", "secret") is None
