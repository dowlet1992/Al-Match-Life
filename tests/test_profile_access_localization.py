from backend.profile_routes import profile_access_copy


def test_profile_access_messages_are_complete_for_supported_languages():
    for language in ("ru", "en", "de", "tr"):
        copy = profile_access_copy(language)
        assert set(copy) == {
            "blocked_title", "blocked_message", "private_title",
            "private_message", "friends_title", "friends_message",
        }
        assert all(copy.values())


def test_profile_access_copy_falls_back_to_english():
    assert profile_access_copy("fr") == profile_access_copy("en")
