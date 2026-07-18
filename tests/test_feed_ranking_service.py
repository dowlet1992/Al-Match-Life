from backend.models import User
from backend.services import feed_ranking_service


def make_user(email="alice@example.com"):
    return User(
        "Alice",
        28,
        email,
        "hashed",
        "Germany",
        "Builder",
        "Founder",
        "Partners",
        ["English"],
        ["Build AI"],
        ["AI"],
        ["Sales"],
    )


def deps_for(users_by_email, settings=None):
    settings = settings or {}

    return {
        "calculate_ai_learning_boost": lambda user_email, post, content_language: (0, []),
        "can_view_feed_post": lambda viewer_email, post: True,
        "clean_text": lambda value: str(value or "").strip(),
        "content_languages": lambda: {"en": "English", "de": "Deutsch", "unknown": "Unknown"},
        "detect_content_language": lambda text: "en",
        "find_user_by_email": lambda email: users_by_email.get(str(email).lower()),
        "get_current_language": lambda user: "en",
        "get_user_language_signals": lambda user: ["en"],
        "normalize_content_language_code": lambda value: value if value in {"en", "de"} else "unknown",
        "normalize_email": lambda value: str(value or "").strip().lower(),
        "normalize_user_ai_settings": lambda email: settings,
        "score_language_match": lambda user, language: (40 if language == "en" else 5, "Language match" if language == "en" else ""),
        "supported_languages": lambda: {"en": "English", "de": "Deutsch"},
    }


def test_rank_feed_posts_prioritizes_language_interest_and_engagement():
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    users_by_email = {"alice@example.com": alice, "bob@example.com": bob}
    posts = [
        {
            "id": 1,
            "email": "bob@example.com",
            "language": "de",
            "type": "Idea",
            "text": "General design note",
            "location": "",
            "hashtags": [],
            "likes": [],
            "comments": [],
            "saves": [],
        },
        {
            "id": 2,
            "email": "bob@example.com",
            "language": "en",
            "type": "Idea",
            "text": "AI product for founders",
            "location": "Germany",
            "hashtags": ["ai"],
            "likes": ["x", "y"],
            "comments": [{"text": "nice"}],
            "saves": ["z"],
        },
    ]

    result = feed_ranking_service.rank_feed_posts(alice, posts, deps_for(users_by_email))

    assert result["ranked_posts"][0]["post"]["id"] == 2
    assert result["ranked_posts"][0]["score"] > result["ranked_posts"][1]["score"]
    assert "Language match" in result["ranked_posts"][0]["ai_reasons"]
    assert any("Совпадает с вашим интересом" in reason for reason in result["ranked_posts"][0]["ai_reasons"])
    assert result["user_language_names"] == ["English"]


def test_rank_feed_posts_detects_unknown_language_and_marks_feed_changed():
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    post = {
        "id": 1,
        "email": "bob@example.com",
        "language": "",
        "type": "Idea",
        "text": "AI product",
        "location": "",
        "hashtags": [],
        "likes": [],
        "comments": [],
        "saves": [],
    }

    result = feed_ranking_service.rank_feed_posts(
        alice,
        [post],
        deps_for({"alice@example.com": alice, "bob@example.com": bob}),
    )

    assert result["feed_changed"] is True
    assert post["language"] == "en"


def test_rank_feed_posts_respects_disabled_ai_recommendations_order():
    alice = make_user("alice@example.com")
    bob = make_user("bob@example.com")
    posts = [
        {"id": 1, "email": "bob@example.com", "language": "en", "type": "Idea", "text": "AI", "location": "", "hashtags": [], "likes": [], "comments": [], "saves": []},
        {"id": 2, "email": "bob@example.com", "language": "en", "type": "Idea", "text": "AI", "location": "", "hashtags": [], "likes": [], "comments": [], "saves": []},
    ]

    result = feed_ranking_service.rank_feed_posts(
        alice,
        posts,
        deps_for(
            {"alice@example.com": alice, "bob@example.com": bob},
            {"ai_recommendations": False, "ai_activity_analysis": True},
        ),
    )

    assert [item["post"]["id"] for item in result["ranked_posts"]] == [2, 1]
    assert result["ranked_posts"][0]["ai_reasons"] == ["AI-рекомендации выключены: показана обычная лента"]
