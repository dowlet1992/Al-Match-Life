from backend.models import User
from backend.services import story_view_service


def make_user(email, name):
    return User(name, 28, email, "hashed", "Germany", "", "", "", [], [], [], [])


def deps(**overrides):
    values = {
        "can_view_user_stories": lambda viewer_email, owner_email: True,
        "is_blocked": lambda first_email, second_email: False,
        "is_story_active": lambda story: True,
        "log_security_event": lambda *args: None,
        "normalize_email": lambda value: str(value or "").strip().lower(),
    }
    values.update(overrides)
    return values


def test_prepare_story_view_marks_view_once_and_sorts_active_stories():
    viewer = make_user("alice@example.com", "Alice")
    owner = make_user("bob@example.com", "Bob")
    stories_data = {
        "stories": [
            {"id": 2, "email": "bob@example.com", "created_at": "2026-07-18 12:00:00", "views": []},
            {"id": 1, "email": "bob@example.com", "created_at": "2026-07-18 10:00:00", "views": ["Alice@Example.com"]},
            {"id": 3, "email": "carol@example.com", "created_at": "2026-07-18 09:00:00", "views": []},
        ]
    }

    result = story_view_service.prepare_story_view(viewer, owner, stories_data, deps())

    assert result["status"] == "ok"
    assert result["changed"] is True
    assert [story["id"] for story in result["owner_stories"]] == [1, 2]
    assert stories_data["stories"][0]["views"] == ["alice@example.com"]
    assert stories_data["stories"][1]["views"] == ["Alice@Example.com"]
    assert result["story_count_text"] == "2 историй"


def test_prepare_story_view_blocks_restricted_viewer():
    result = story_view_service.prepare_story_view(
        make_user("alice@example.com", "Alice"),
        make_user("bob@example.com", "Bob"),
        {"stories": []},
        deps(can_view_user_stories=lambda viewer_email, owner_email: False),
    )

    assert result["status"] == "restricted"
    assert result["changed"] is False


def test_prepare_story_view_logs_blocked_attempt():
    logs = []

    result = story_view_service.prepare_story_view(
        make_user("alice@example.com", "Alice"),
        make_user("bob@example.com", "Bob"),
        {"stories": []},
        deps(
            is_blocked=lambda first_email, second_email: first_email == "alice@example.com",
            log_security_event=lambda event_type, email, details: logs.append((event_type, email, details)),
        ),
    )

    assert result["status"] == "blocked"
    assert logs == [("story_view_blocked", "alice@example.com", "Blocked story view attempt to bob@example.com")]


def test_prepare_story_view_returns_empty_when_no_active_owner_stories():
    result = story_view_service.prepare_story_view(
        make_user("alice@example.com", "Alice"),
        make_user("bob@example.com", "Bob"),
        {"stories": [{"id": 1, "email": "bob@example.com"}]},
        deps(is_story_active=lambda story: False),
    )

    assert result["status"] == "empty"
    assert result["owner_stories"] == []


def test_prepare_story_view_counts_owner_unique_viewers():
    owner = make_user("bob@example.com", "Bob")
    stories_data = {
        "stories": [
            {"id": 1, "email": "bob@example.com", "created_at": "2026-07-18 10:00:00", "views": ["alice@example.com", "carol@example.com"]},
            {"id": 2, "email": "bob@example.com", "created_at": "2026-07-18 11:00:00", "views": ["Alice@Example.com", "bob@example.com"]},
        ]
    }

    result = story_view_service.prepare_story_view(owner, owner, stories_data, deps())

    assert result["status"] == "ok"
    assert result["views_count"] == 2
    assert result["story_count_text"] == "2 историй · 2 просмотров"
