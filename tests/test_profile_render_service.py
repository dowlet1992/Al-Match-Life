from backend.services import profile_render_service


def clean_text(value):
    return str(value or "").strip()


def test_build_profile_posts_normalizes_media_hashtags_and_counts():
    posts = profile_render_service.build_profile_posts([{
        "id": "42", "type": "Project", "text": "<AI platform>", "date": "2026-07-18",
        "media_items": [
            {"url": "/media-files/image.jpg", "type": "image"},
            {"url": "/static/clip.mp4", "type": "video"},
            {"url": "https://tracker.example/voice.mp3", "type": "audio"},
        ],
        "hashtags": ["#ai", " founders "], "likes": ["a", "b"], "comments": ["c"], "saves": [],
    }], clean_text)

    assert posts[0]["id"] == "42"
    assert posts[0]["text"] == "<AI platform>"
    assert [media["type"] for media in posts[0]["media"]] == ["image", "video"]
    assert posts[0]["hashtags"] == ["ai", "founders"]
    assert (posts[0]["likes"], posts[0]["comments"], posts[0]["saves"]) == (2, 1, 0)


def test_build_profile_posts_supports_local_legacy_media():
    posts = profile_render_service.build_profile_posts([
        {"id": 1, "media_url": "/static/legacy.jpg", "media_type": "image"}
    ], clean_text)
    assert posts[0]["media"] == [{"url": "/static/legacy.jpg", "type": "image"}]


def test_build_profile_tabs_and_stats():
    tabs = profile_render_service.build_profile_tabs("media", {"all": 5, "media": 3})
    visible = profile_render_service.build_profile_stats({"all": 7}, 2, 3, True)
    hidden = profile_render_service.build_profile_stats({"all": 7}, 2, 3, False)
    assert [tab["key"] for tab in tabs] == ["all", "news", "projects", "media", "proof"]
    assert tabs[3]["count"] == 3
    assert visible == {"visible": True, "activity": 7, "following": 2, "followers": 3}
    assert hidden["visible"] is False


def test_build_profile_header_and_info_clean_empty_values():
    class User:
        age = "не указано"
        languages = ["English", "none", "Deutsch"]
        goals = "Build; null; Launch"
        interests = []
        skills = ["AI"]
        profession = "Founder"
        country = "Germany"
        bio = "<hello>"

    labels = {"age": "Age", "languages": "Languages", "goals": "Goals", "interests": "Interests", "skills": "Skills"}
    header = profile_render_service.build_profile_header(User(), clean_text)
    info = profile_render_service.build_profile_info(User(), clean_text, labels)
    assert header == {"meta": "Founder · Germany", "bio": "<hello>"}
    assert info == [
        {"label": "Languages", "value": "English, Deutsch"},
        {"label": "Goals", "value": "Build, Launch"},
        {"label": "Skills", "value": "AI"},
    ]
