from backend.services import feed_privacy_service


def test_post_content_filters_block_adult_and_sensitive_content():
    settings = {"adult_content_filter": True, "sensitive_content_filter": True}

    assert feed_privacy_service.post_matches_content_filters(settings, {
        "text": "Professional AI update",
    }) is True
    assert feed_privacy_service.post_matches_content_filters(settings, {
        "text": "NSFW adult content",
    }) is False
    assert feed_privacy_service.post_matches_content_filters(settings, {
        "moderation_flags": ["sensitive"],
    }) is False


def test_post_content_filters_respect_disabled_filters():
    settings = {"adult_content_filter": False, "sensitive_content_filter": False}

    assert feed_privacy_service.post_matches_content_filters(settings, {
        "content_rating": "adult",
        "text": "nsfw",
    }) is True


def test_can_view_feed_post_respects_relationship_filters():
    post = {"email": "bob@example.com", "text": "Visible"}

    assert feed_privacy_service.can_view_feed_post(
        "alice@example.com",
        post,
        {"adult_content_filter": True, "sensitive_content_filter": True},
        lambda one, two: False,
        lambda one, two: False,
    ) is True

    assert feed_privacy_service.can_view_feed_post(
        "alice@example.com",
        post,
        {"adult_content_filter": True, "sensitive_content_filter": True},
        lambda one, two: one == "bob@example.com" and two == "alice@example.com",
        lambda one, two: False,
    ) is False

    assert feed_privacy_service.can_view_feed_post(
        "alice@example.com",
        post,
        {"adult_content_filter": True, "sensitive_content_filter": True},
        lambda one, two: False,
        lambda one, two: one == "alice@example.com" and two == "bob@example.com",
    ) is False
