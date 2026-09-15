from backend.media_access_cache import MediaAccessCache
from backend.services.media_access_service import can_access_media_file


def dependencies(**overrides):
    deps = {
        "cache": MediaAccessCache(ttl_seconds=2, max_entries=10),
        "can_view_feed_post": lambda viewer, post: True,
        "can_view_user_stories": lambda viewer, owner: True,
        "load_feed": lambda: {"posts": []},
        "load_messages": lambda: [],
        "load_stories": lambda: {"stories": []},
        "normalize_email": lambda value: str(value or "").strip().lower(),
    }
    deps.update(overrides)
    return deps


def test_media_access_service_rejects_orphan_private_media():
    deps = dependencies()

    assert can_access_media_file("chat_orphan.png", "alice@example.com", deps) is False
    assert can_access_media_file("story_orphan.jpg", "alice@example.com", deps) is False
    assert can_access_media_file("post_orphan.mp4", "alice@example.com", deps) is False


def test_media_access_service_allows_only_chat_participants():
    filename = "chat_owner_token.png"
    deps = dependencies(load_messages=lambda: [{
        "from": "alice@example.com",
        "to": "bob@example.com",
        "media_url": f"/media-files/{filename}",
    }])

    assert can_access_media_file(filename, "alice@example.com", deps) is True
    assert can_access_media_file(filename, "charlie@example.com", deps) is False
