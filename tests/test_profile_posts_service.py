from backend.services import profile_posts_service


def deps():
    return {
        "clean_text": lambda value: str(value or "").strip(),
        "normalize_email": lambda value: str(value or "").strip().lower(),
    }


def test_profile_post_summary_filters_owner_posts_and_counts_tabs():
    posts = [
        {"id": 1, "email": "alice@example.com", "type": "Новость", "created_at": "1"},
        {"id": 2, "author_email": "Alice@Example.com", "type": "Проект", "created_at": "2"},
        {"id": 3, "email": "alice@example.com", "type": "Proof", "created_at": "3"},
        {"id": 4, "email": "alice@example.com", "type": "Life", "media_items": [{"url": "/a.jpg"}], "created_at": "4"},
        {"id": 5, "email": "bob@example.com", "type": "Новость", "created_at": "5"},
    ]

    summary = profile_posts_service.profile_post_summary(posts, "alice@example.com", "all", deps())

    assert summary["current_tab"] == "all"
    assert [post["id"] for post in summary["user_posts"]] == [1, 2, 3, 4]
    assert [post["id"] for post in summary["filtered_posts"]] == [4, 3, 2, 1]
    assert summary["counts"] == {
        "all": 4,
        "news": 1,
        "projects": 1,
        "media": 1,
        "proof": 1,
    }


def test_profile_post_summary_filters_requested_tab():
    posts = [
        {"id": 1, "email": "alice@example.com", "type": "Идея"},
        {"id": 2, "email": "alice@example.com", "type": "Поиск партнёра"},
        {"id": 3, "email": "alice@example.com", "type": "Update", "media_url": "/photo.jpg"},
    ]

    projects = profile_posts_service.profile_post_summary(posts, "alice@example.com", "projects", deps())
    media = profile_posts_service.profile_post_summary(posts, "alice@example.com", "media", deps())

    assert [post["id"] for post in projects["filtered_posts"]] == [2]
    assert [post["id"] for post in media["filtered_posts"]] == [3]


def test_profile_post_summary_falls_back_to_all_for_unknown_tab():
    summary = profile_posts_service.profile_post_summary(
        [{"id": 1, "email": "alice@example.com", "type": "Unknown"}],
        "alice@example.com",
        "bad-tab",
        deps(),
    )

    assert summary["current_tab"] == "all"
    assert [post["id"] for post in summary["filtered_posts"]] == [1]
