from datetime import datetime
from io import BytesIO

from werkzeug.datastructures import FileStorage

from backend.models import User
from backend.services import story_creation_service


def make_user():
    return User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])


def make_file(filename, content=b"media"):
    return FileStorage(stream=BytesIO(content), filename=filename, content_type="image/jpeg")


def test_create_stories_saves_valid_image(tmp_path):
    result = story_creation_service.create_stories(make_user(), [make_file("My Story.JPG")], {"stories": []}, {
        "allowed_mime_type": lambda uploaded_file: True,
        "log_security_event": lambda *args: None,
        "now": lambda: datetime(2026, 7, 18, 11, 22, 33, 456789),
        "token_urlsafe": lambda length: "token",
        "upload_folder": str(tmp_path),
    })

    story = result["stories_data"]["stories"][0]

    assert result["created_count"] == 1
    assert story["id"] == 1
    assert story["email"] == "alice@example.com"
    assert story["media_type"] == "image"
    assert story["media_url"].endswith("_My_Story.JPG")
    assert story["created_at"] == "2026-07-18 11:22:33"
    assert (tmp_path / "story_alice_at_example_com_token_20260718112233456789_My_Story.JPG").exists()


def test_create_stories_rejects_invalid_file_and_logs(tmp_path):
    logs = []

    result = story_creation_service.create_stories(make_user(), [make_file("archive.zip")], {"stories": []}, {
        "allowed_mime_type": lambda uploaded_file: True,
        "log_security_event": lambda event_type, email, details: logs.append((event_type, email, details)),
        "upload_folder": str(tmp_path),
    })

    assert result["created_count"] == 0
    assert result["stories_data"]["stories"] == []
    assert logs == [("story_upload_rejected", "alice@example.com", "Unsupported story file extension")]


def test_create_stories_uses_next_numeric_id_and_keeps_last_1000(tmp_path):
    existing = [{"id": index, "email": "old@example.com"} for index in range(1, 1002)]

    result = story_creation_service.create_stories(make_user(), [make_file("clip.mp4")], {"stories": existing}, {
        "allowed_mime_type": lambda uploaded_file: True,
        "log_security_event": lambda *args: None,
        "now": lambda: datetime(2026, 7, 18, 12, 0, 0),
        "token_urlsafe": lambda length: "video",
        "upload_folder": str(tmp_path),
    })

    stories = result["stories_data"]["stories"]

    assert result["created_count"] == 1
    assert len(stories) == 1000
    assert stories[-1]["id"] == 1002
    assert stories[-1]["media_type"] == "video"
    assert stories[0]["id"] == 3
