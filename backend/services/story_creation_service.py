import os
import secrets
from datetime import datetime

from werkzeug.utils import secure_filename


IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "m4v"}


def next_story_id(stories):
    numeric_ids = []
    for story in stories:
        try:
            numeric_ids.append(int(story.get("id", 0)))
        except Exception:
            continue

    return max(numeric_ids) + 1 if numeric_ids else 1


def story_media_type_for_filename(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"

    return ""


def normalize_stories_list(stories_data):
    stories = stories_data.get("stories", []) if isinstance(stories_data, dict) else []
    if not isinstance(stories, list):
        return []
    return stories


def create_stories(user, uploaded_files, stories_data, deps):
    stories_data = stories_data if isinstance(stories_data, dict) else {}
    stories = normalize_stories_list(stories_data)
    next_id = next_story_id(stories)
    created_count = 0

    for uploaded_file in uploaded_files[:10]:
        if not uploaded_file or not uploaded_file.filename:
            continue

        filename = secure_filename(uploaded_file.filename)
        media_type = story_media_type_for_filename(filename)

        if not media_type:
            deps["log_security_event"]("story_upload_rejected", user.email, "Unsupported story file extension")
            continue

        if not deps["allowed_mime_type"](uploaded_file):
            deps["log_security_event"]("story_upload_rejected", user.email, "Invalid story media content")
            continue

        safe_email = secure_filename(user.email.replace("@", "_at_").replace(".", "_"))
        now = deps.get("now", datetime.now)()
        token = deps.get("token_urlsafe", secrets.token_urlsafe)(8)
        stored_name = f"story_{safe_email}_{token}_{now.strftime('%Y%m%d%H%M%S%f')}_{filename}"
        upload_path = os.path.join(deps["upload_folder"], stored_name)
        uploaded_file.save(upload_path)

        stories.append({
            "id": next_id,
            "email": user.email,
            "name": user.name,
            "media_url": f"/static/uploads/{stored_name}",
            "media_type": media_type,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "views": [],
        })
        next_id += 1
        created_count += 1

    stories_data["stories"] = stories[-1000:]

    return {
        "stories_data": stories_data,
        "created_count": created_count,
    }
