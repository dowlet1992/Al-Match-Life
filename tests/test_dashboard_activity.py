import app
from backend.models import User


def make_user(email, name="Alice"):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def test_calculate_dashboard_activity_count_returns_zero_for_no_posts():
    alice = make_user("alice@example.com")
    assert app.calculate_dashboard_activity_count(alice, []) == 0


def test_calculate_dashboard_activity_count_includes_engagement_actions():
    alice = make_user("alice@example.com")
    posts = [
        {
            "id": 1,
            "email": "alice@example.com",
            "likes": ["bob@example.com"],
            "saves": ["alice@example.com"],
            "comments": [
                {"author": "alice@example.com", "text": "Nice post"},
                {"author": "bob@example.com", "text": "Thanks"},
            ],
            "shares": [
                {"email": "alice@example.com", "to": "bob@example.com"},
            ],
        },
        {
            "id": 2,
            "email": "bob@example.com",
            "likes": ["alice@example.com"],
            "saves": [],
            "comments": [],
            "shares": [],
        },
    ]

    assert app.calculate_dashboard_activity_count(alice, posts) == 5
