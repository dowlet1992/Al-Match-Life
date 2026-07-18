from backend.models import User
from backend.services import privacy_service, profile_service


def test_profile_service_onboarding_and_update_profile():
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    assert profile_service.user_needs_onboarding(user) is True

    profile_service.apply_onboarding(
        user,
        {
            "looking_for": "team",
            "profession": "Founder",
            "goals": "startup, growth",
            "interests": "AI, product",
            "skills": "strategy, sales",
            "languages": "English, German",
        },
    )

    assert user.onboarding_completed is True
    assert user.looking_for == "team"
    assert user.goals == ["startup", "growth"]
    assert profile_service.user_needs_onboarding(user) is False

    profile_service.update_profile(user, {"bio": "<b>Hello</b>", "skills": ["AI", "sales"]})
    assert user.bio == "Hello"
    assert user.skills == ["AI", "sales"]


def test_profile_service_skip_onboarding():
    user = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])

    profile_service.skip_onboarding(user)

    assert user.onboarding_skipped is True
    assert user.onboarding_completed is False
    assert profile_service.user_needs_onboarding(user) is False


def test_privacy_service_normalize_and_build_update():
    settings = privacy_service.normalize_settings({"allow_messages": False})

    assert settings["message_permission"] == "none"

    updated, error = privacy_service.build_update(
        settings,
        {"show_in_search": False, "message_permission": "friends"},
    )

    assert error == ""
    assert updated["show_in_search"] is False
    assert updated["message_permission"] == "friends"
    assert updated["allow_messages"] is True
    assert updated["friends_only_messages"] is True


def test_privacy_service_rejects_invalid_message_permission():
    updated, error = privacy_service.build_update({}, {"message_permission": "bad"})

    assert updated is None
    assert error == "Invalid message permission"
