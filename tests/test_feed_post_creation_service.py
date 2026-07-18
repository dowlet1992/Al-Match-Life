from datetime import datetime
from io import BytesIO

from werkzeug.datastructures import FileStorage, MultiDict

from backend.models import User
from backend.services import feed_post_creation_service


def make_user():
    return User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])


def test_build_web_post_normalizes_fields_and_appends_post(tmp_path):
    user = make_user()
    feed_data = {"posts": [{"id": 4, "text": "old"}]}
    form = MultiDict({
        "type": "idea",
        "text": " Build useful AI ",
        "location": " Berlin ",
        "hashtags": "#ai, #founders #ai",
    })

    result = feed_post_creation_service.build_web_post(user, form, [], feed_data, {
        "allowed_mime_type": lambda uploaded_file: True,
        "clean_text": lambda value: str(value).strip(),
        "detect_content_language": lambda text: "en",
        "log_security_event": lambda *args: None,
        "normalize_content_language_code": lambda value: value or "unknown",
        "upload_folder": str(tmp_path),
    })

    assert result["ok"] is True
    assert result["post"]["id"] == 5
    assert result["post"]["type"] == "Идея"
    assert result["post"]["text"] == "Build useful AI"
    assert result["post"]["location"] == "Berlin"
    assert result["post"]["hashtags"] == ["ai", "founders"]
    assert result["post"]["language"] == "en"
    assert feed_data["posts"][-1] == result["post"]


def test_build_web_post_saves_valid_media(tmp_path):
    user = make_user()
    uploaded_file = FileStorage(
        stream=BytesIO(b"fake image"),
        filename="My Photo.JPG",
        content_type="image/jpeg",
    )

    result = feed_post_creation_service.build_web_post(user, MultiDict({"text": ""}), [uploaded_file], {"posts": []}, {
        "allowed_mime_type": lambda uploaded_file: True,
        "clean_text": lambda value: str(value).strip(),
        "detect_content_language": lambda text: "unknown",
        "log_security_event": lambda *args: None,
        "normalize_content_language_code": lambda value: value or "unknown",
        "now": lambda: datetime(2026, 7, 18, 10, 20, 30, 123456),
        "token_urlsafe": lambda length: "token",
        "upload_folder": str(tmp_path),
    })

    assert result["ok"] is True
    assert result["post"]["media_type"] == "image"
    assert result["post"]["media_url"].endswith("_My_Photo.JPG")
    assert (tmp_path / "post_alice_at_example_com_token_20260718102030123456_My_Photo.JPG").exists()


def test_build_web_post_rejects_empty_post(tmp_path):
    result = feed_post_creation_service.build_web_post(make_user(), MultiDict({"text": ""}), [], {"posts": []}, {
        "allowed_mime_type": lambda uploaded_file: True,
        "clean_text": lambda value: str(value).strip(),
        "detect_content_language": lambda text: "unknown",
        "log_security_event": lambda *args: None,
        "normalize_content_language_code": lambda value: value or "unknown",
        "upload_folder": str(tmp_path),
    })

    assert result["ok"] is False
    assert result["reason"] == "empty_post"
    assert result["post"] is None
