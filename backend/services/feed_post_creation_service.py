import os
import secrets
from datetime import datetime

from werkzeug.utils import secure_filename

from backend.services import feed_service


POST_TYPE_ALIASES = {
    "news": "Новость",
    "nevs": "Новость",
    "новости": "Новость",
    "новость": "Новость",
    "idea": "Идея",
    "идея": "Идея",
    "мысль": "Идея",
    "project": "Проект",
    "проект": "Проект",
    "partner": "Поиск партнёра",
    "поиск партнёра": "Поиск партнёра",
    "достижение": "Достижение",
    "achievement": "Достижение",
    "proof": "Proof",
}

ALLOWED_POST_TYPES = {"Новость", "Идея", "Проект", "Поиск партнёра", "Достижение", "Proof"}

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm", "m4v"}
AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "webm"}


def normalize_post_type(raw_post_type, clean_text):
    post_type = clean_text(raw_post_type or "").strip()
    normalized_key = post_type.lower()
    post_type = POST_TYPE_ALIASES.get(normalized_key, post_type)

    if post_type not in ALLOWED_POST_TYPES:
        return "Новость"

    return post_type


def parse_post_hashtags(hashtags_raw, clean_text):
    hashtags = []
    hashtags_text = clean_text(hashtags_raw or "").strip()

    if not hashtags_text:
        return hashtags

    for raw_tag in hashtags_text.replace(",", " ").split():
        clean_tag = clean_text(raw_tag).replace("#", "").strip()
        if clean_tag and clean_tag not in hashtags:
            hashtags.append(clean_tag[:40])

    return hashtags


def media_type_for_filename(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in AUDIO_EXTENSIONS:
        return "audio"

    return ""


def save_post_media_files(user, files, deps):
    media_items = []

    for uploaded_file in files[:10]:
        if not uploaded_file or not uploaded_file.filename:
            continue

        filename = secure_filename(uploaded_file.filename)
        current_type = media_type_for_filename(filename)
        if not current_type:
            deps["log_security_event"]("upload_rejected", user.email, "Unsupported post media file extension")
            continue

        if not deps["allowed_mime_type"](uploaded_file):
            deps["log_security_event"]("upload_rejected", user.email, "Invalid post media file content")
            continue

        safe_email = secure_filename(user.email.replace("@", "_at_").replace(".", "_"))
        timestamp = deps.get("now", datetime.now)().strftime("%Y%m%d%H%M%S%f")
        token = deps.get("token_urlsafe", secrets.token_urlsafe)(8)
        new_filename = f"post_{safe_email}_{token}_{timestamp}_{filename}"

        upload_path = os.path.join(deps["upload_folder"], new_filename)
        uploaded_file.save(upload_path)

        media_items.append({
            "url": f"/static/uploads/{new_filename}",
            "type": current_type,
            "name": filename,
        })

    return media_items


def build_web_post(user, form, files, feed_data, deps):
    clean_text = deps["clean_text"]
    raw_post_type = form.get("type", "")
    post_type = normalize_post_type(raw_post_type, clean_text)
    text = clean_text(form.get("text", "")).strip()
    location = clean_text(form.get("location", "")).strip()
    hashtags_raw = clean_text(form.get("hashtags", "")).strip()
    content_language = deps["normalize_content_language_code"](form.get("language", ""))

    if not form.get("language", ""):
        content_language = deps["detect_content_language"](" ".join([post_type, text, location, hashtags_raw]))

    hashtags = parse_post_hashtags(hashtags_raw, clean_text)
    media_items = save_post_media_files(user, files, deps)

    if not text and not media_items:
        return {
            "ok": False,
            "reason": "empty_post",
            "feed_data": feed_data,
            "post": None,
        }

    post = feed_service.create_text_post(
        user,
        text,
        post_type=post_type,
        location=location,
        hashtags=hashtags,
        language=content_language,
    )

    if media_items:
        post["media_url"] = media_items[0].get("url", "")
        post["media_type"] = media_items[0].get("type", "")
        post["media_items"] = media_items

    feed_service.append_post(feed_data, post)

    return {
        "ok": True,
        "reason": "",
        "feed_data": feed_data,
        "post": post,
    }
