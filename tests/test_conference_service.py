import jwt

from backend.services import conference_service


def test_conference_token_is_short_lived_and_room_scoped():
    token = conference_service.issue_access_token(
        "novix-key", "a-secure-secret-at-least-32-characters", "novix_room", "uuid-1", "Alice", now=1000,
    )
    payload = jwt.decode(token, "a-secure-secret-at-least-32-characters", algorithms=["HS256"], options={"verify_exp": False})
    assert payload["sub"] == "uuid-1"
    assert payload["exp"] == 1000 + conference_service.TOKEN_TTL_SECONDS
    assert payload["video"]["room"] == "novix_room"
    assert payload["video"]["roomJoin"] is True


def test_conference_participants_are_unique_and_bounded():
    normalized = conference_service.normalize_participants(
        "OWNER@example.com", ["a@example.com", "A@example.com", "b@example.com", "c@example.com", "d@example.com"],
        lambda value: str(value).strip().lower(),
    )
    assert normalized == ["owner@example.com", "a@example.com", "b@example.com", "c@example.com"]
