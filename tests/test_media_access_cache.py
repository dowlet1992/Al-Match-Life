from backend.media_access_cache import MediaAccessCache


def test_media_access_cache_is_scoped_by_viewer_and_expires():
    now = [100.0]
    cache = MediaAccessCache(ttl_seconds=2, max_entries=10, clock=lambda: now[0])

    cache.remember_allowed("alice@example.com", "chat_file.png")

    assert cache.allows("alice@example.com", "chat_file.png") is True
    assert cache.allows("bob@example.com", "chat_file.png") is False
    now[0] = 102.0
    assert cache.allows("alice@example.com", "chat_file.png") is False


def test_media_access_cache_is_bounded_and_evicts_oldest_entry():
    cache = MediaAccessCache(ttl_seconds=10, max_entries=2, clock=lambda: 100.0)

    cache.remember_allowed("alice", "one")
    cache.remember_allowed("alice", "two")
    cache.remember_allowed("alice", "three")

    assert cache.allows("alice", "one") is False
    assert cache.allows("alice", "two") is True
    assert cache.allows("alice", "three") is True
