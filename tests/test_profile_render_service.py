from backend.services import profile_render_service


def clean_text(value):
    return str(value or "").strip()


def safe_text(value):
    return clean_text(value).replace("<", "&lt;").replace(">", "&gt;")


def test_render_profile_post_card_includes_media_hashtags_and_counts():
    html = profile_render_service.render_profile_post_card(
        {
            "id": "42",
            "type": "Проект",
            "text": "<AI platform>",
            "date": "2026-07-18",
            "media_items": [
                {"url": "/image.jpg", "type": "image"},
                {"url": "/clip.mp4", "type": "video"},
                {"url": "/voice.mp3", "type": "audio"},
            ],
            "hashtags": ["#ai", " founders "],
            "likes": ["a", "b"],
            "comments": ["c"],
            "saves": [],
        },
        "viewer@example.com",
        clean_text,
        safe_text,
    )

    assert "/post/viewer@example.com/42" in html
    assert "Проект" in html
    assert "&lt;AI platform&gt;" in html
    assert 'src="/image.jpg"' in html
    assert 'src="/clip.mp4"' in html
    assert 'src="/voice.mp3"' in html
    assert "#ai" in html
    assert "#founders" in html
    assert "♡ 2" in html
    assert "💬 1" in html
    assert "🔖 0" in html


def test_render_profile_post_card_supports_legacy_media_url():
    html = profile_render_service.render_profile_post_card(
        {"id": 1, "media_url": "/legacy.jpg", "media_type": "image"},
        "viewer@example.com",
        clean_text,
        safe_text,
    )

    assert 'src="/legacy.jpg"' in html


def test_render_profile_posts_returns_tab_specific_empty_state():
    assert "Пока нет фото или видео." in profile_render_service.render_profile_posts(
        [],
        "media",
        "viewer@example.com",
        clean_text,
        safe_text,
    )
    assert "Пока нет Proof-публикаций." in profile_render_service.render_profile_posts(
        [],
        "proof",
        "viewer@example.com",
        clean_text,
        safe_text,
    )


def test_render_profile_tabs_marks_active_tab_and_preserves_viewer():
    html = profile_render_service.render_profile_tabs(
        "media",
        {"all": 5, "news": 1, "projects": 2, "media": 3, "proof": 4},
        "owner@example.com",
        "viewer@example.com",
        safe_text,
    )

    assert "/profile/owner@example.com?viewer=viewer@example.com&tab=media" in html
    assert 'profile-tab active' in html
    assert "<strong>3</strong>" in html


def test_render_profile_stats_handles_visible_and_hidden_activity():
    visible = profile_render_service.render_profile_stats(
        "owner@example.com",
        "viewer@example.com",
        {"all": 7},
        2,
        3,
        True,
        safe_text,
    )
    hidden = profile_render_service.render_profile_stats(
        "owner@example.com",
        "viewer@example.com",
        {"all": 7},
        2,
        3,
        False,
        safe_text,
    )

    assert "/profile/owner@example.com?viewer=viewer@example.com&tab=all" in visible
    assert "<strong>7</strong>" in visible
    assert "/following/owner@example.com" in visible
    assert "<strong>—</strong>" in hidden


def test_render_profile_info_cleans_empty_values_and_lists():
    class User:
        age = "не указано"
        languages = ["English", "none", "Deutsch"]
        goals = "Build; null; Launch"
        interests = []
        skills = ["AI"]
        profession = "Founder"
        country = "Germany"
        bio = "<hello>"

    meta_html, bio_html = profile_render_service.render_profile_header_text(User(), clean_text, safe_text)
    info_html = profile_render_service.render_profile_info(User(), clean_text, safe_text)

    assert "Founder · Germany" in meta_html
    assert "&lt;hello&gt;" in bio_html
    assert "English, Deutsch" in info_html
    assert "Build, Launch" in info_html
    assert "AI" in info_html
    assert "не указано" not in info_html


def test_render_profile_info_empty_state():
    class User:
        age = ""
        languages = []
        goals = []
        interests = []
        skills = []

    assert "Профиль пока без подробной информации." in profile_render_service.render_profile_info(
        User(),
        clean_text,
        safe_text,
    )
