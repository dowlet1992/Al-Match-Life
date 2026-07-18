SENSITIVE_CONTENT_KEYWORDS = {
    "violence",
    "violent",
    "blood",
    "weapon",
    "hate",
    "abuse",
    "selfharm",
    "self-harm",
    "суицид",
    "насилие",
    "кровь",
    "оружие",
    "ненависть",
    "şiddet",
    "kan",
    "silah",
}

ADULT_CONTENT_KEYWORDS = {
    "adult",
    "nsfw",
    "sex",
    "sexual",
    "porn",
    "18+",
    "эротика",
    "порно",
    "взрослый",
    "yetişkin",
    "cinsel",
}


def normalize_email(value):
    return str(value or "").strip().lower()


def clean_text(value):
    return str(value or "").strip()


def post_matches_content_filters(settings, post):
    settings = settings if isinstance(settings, dict) else {}

    if settings.get("sensitive_content_filter", True) is not True and settings.get("adult_content_filter", True) is not True:
        return True

    if not isinstance(post, dict):
        return True

    moderation_flags = post.get("moderation_flags", [])
    if not isinstance(moderation_flags, list):
        moderation_flags = []

    content_rating = clean_text(post.get("content_rating", "")).lower()
    is_sensitive = post.get("sensitive") is True or content_rating in {"sensitive", "mature"} or "sensitive" in moderation_flags
    is_adult = post.get("adult") is True or post.get("nsfw") is True or content_rating in {"adult", "nsfw"} or "adult" in moderation_flags or "nsfw" in moderation_flags

    text_parts = [
        str(post.get("type", "")),
        str(post.get("text", "")),
        str(post.get("location", "")),
        " ".join([str(item) for item in post.get("hashtags", []) if item]),
    ]
    searchable_text = " ".join(text_parts).lower()

    if any(keyword in searchable_text for keyword in SENSITIVE_CONTENT_KEYWORDS):
        is_sensitive = True

    if any(keyword in searchable_text for keyword in ADULT_CONTENT_KEYWORDS):
        is_adult = True

    if settings.get("adult_content_filter", True) is True and is_adult:
        return False

    if settings.get("sensitive_content_filter", True) is True and is_sensitive:
        return False

    return True


def can_view_feed_post(viewer_email, post, viewer_settings, is_blocked, is_restricted):
    if not isinstance(post, dict):
        return False

    viewer_email = normalize_email(viewer_email)
    author_email = normalize_email(post.get("email") or post.get("author_email") or "")

    if not viewer_email or not author_email:
        return False

    if is_blocked(viewer_email, author_email) or is_blocked(author_email, viewer_email):
        return False

    if is_restricted(viewer_email, author_email) or is_restricted(author_email, viewer_email):
        return False

    if not post_matches_content_filters(viewer_settings, post):
        return False

    return True
