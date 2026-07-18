from backend.models import User
from backend.serializers import message_payload, post_payload, user_payload


def test_user_payload_sanitizes_and_exposes_profile_fields():
    user = User(
        "<b>Alice</b>",
        28,
        "ALICE@EXAMPLE.COM",
        "hashed",
        "Germany",
        "<script>x</script>Builder",
        "Founder",
        "Team",
        ["English"],
        ["startup"],
        ["AI"],
        ["strategy"],
    )
    user.onboarding_completed = True

    payload = user_payload(user)

    assert payload["name"] == "Alice"
    assert payload["email"] == "alice@example.com"
    assert payload["bio"] == "xBuilder"
    assert payload["onboarding_completed"] is True


def test_post_payload_counts_interactions_and_uses_author_payload():
    author = User("Bob", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    post = {
        "id": 1,
        "email": "bob@example.com",
        "type": "Идея",
        "text": "Hello",
        "language": "en",
        "likes": ["a@example.com"],
        "comments": [{"text": "Nice"}],
        "shares": [],
        "saves": ["a@example.com", "b@example.com"],
    }

    payload = post_payload(post, author=author, normalize_language=lambda value: value)

    assert payload["author"]["email"] == "bob@example.com"
    assert payload["likes_count"] == 1
    assert payload["comments_count"] == 1
    assert payload["saves_count"] == 2


def test_message_payload_marks_current_user_messages():
    message = {
        "id": 7,
        "from": "alice@example.com",
        "to": "bob@example.com",
        "message": "<b>Hello</b>",
        "status": "sent",
    }

    payload = message_payload(message, current_email="alice@example.com")

    assert payload["message"] == "Hello"
    assert payload["mine"] is True
