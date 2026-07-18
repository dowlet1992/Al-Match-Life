import bleach


def clean_text(value):
    return bleach.clean(str(value or "").strip(), tags=[], strip=True)


def normalize_email(value):
    return str(value or "").strip().lower()


def user_payload(user):
    if user is None:
        return None

    return {
        "name": clean_text(getattr(user, "name", "")),
        "age": getattr(user, "age", None),
        "email": normalize_email(getattr(user, "email", "")),
        "country": clean_text(getattr(user, "country", "")),
        "bio": clean_text(getattr(user, "bio", "")),
        "profession": clean_text(getattr(user, "profession", "")),
        "looking_for": clean_text(getattr(user, "looking_for", "")),
        "languages": list(getattr(user, "languages", []) or []),
        "goals": list(getattr(user, "goals", []) or []),
        "interests": list(getattr(user, "interests", []) or []),
        "skills": list(getattr(user, "skills", []) or []),
        "trust_score": getattr(user, "trust_score", 0),
        "verified": bool(getattr(user, "verified", False)),
        "profile_completed": bool(getattr(user, "profile_completed", False)),
        "onboarding_completed": bool(getattr(user, "onboarding_completed", False)),
        "onboarding_skipped": bool(getattr(user, "onboarding_skipped", False)),
        "created_at": clean_text(getattr(user, "created_at", "")),
    }


def post_payload(post, author=None, normalize_language=None):
    author_email = normalize_email(post.get("email") or post.get("author_email") or "")
    language_value = post.get("language", "")
    if normalize_language:
        language_value = normalize_language(language_value)
    else:
        language_value = clean_text(language_value)

    return {
        "id": post.get("id"),
        "author": user_payload(author) if author else {
            "email": author_email,
            "name": clean_text(post.get("name") or post.get("author_name") or "User"),
        },
        "type": clean_text(post.get("type", "Публикация")),
        "text": clean_text(post.get("text", "")),
        "location": clean_text(post.get("location", "")),
        "hashtags": list(post.get("hashtags", []) or []),
        "language": language_value,
        "media_url": clean_text(post.get("media_url", "")),
        "media_type": clean_text(post.get("media_type", "")),
        "media_items": list(post.get("media_items", []) or []),
        "date": clean_text(post.get("date", "")),
        "created_at": clean_text(post.get("created_at", "")),
        "likes_count": len(post.get("likes", []) or []),
        "comments_count": len(post.get("comments", []) or []),
        "shares_count": len(post.get("shares", []) or []),
        "saves_count": len(post.get("saves", []) or []),
    }


def message_payload(message, current_email=""):
    current_email = normalize_email(current_email)
    sender_email = normalize_email(message.get("from", ""))
    receiver_email = normalize_email(message.get("to", ""))

    return {
        "id": message.get("id"),
        "from": sender_email,
        "to": receiver_email,
        "message": clean_text(message.get("message", "")),
        "media_url": clean_text(message.get("media_url", "")),
        "media_type": clean_text(message.get("media_type", "")),
        "media_name": clean_text(message.get("media_name", "")),
        "reply_to": clean_text(message.get("reply_to", "")),
        "time": clean_text(message.get("time", "")),
        "status": clean_text(message.get("status", "sent")),
        "mine": bool(current_email and sender_email == current_email),
        "edited": bool(message.get("edited", False)),
        "pinned": bool(message.get("pinned", False)),
        "message_type": clean_text(message.get("message_type", "")),
    }
