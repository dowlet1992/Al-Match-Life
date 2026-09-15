def list_count(post, field_name):
    values = post.get(field_name, [])
    return len(values) if isinstance(values, list) else 0


def profile_clean_value(value, clean_text):
    cleaned = clean_text(value).strip()
    if cleaned.lower() in {"", "nicht angegeben", "не указано", "none", "null", "nan"}:
        return ""
    return cleaned


def profile_list_text(values, clean_text):
    if values is None:
        return ""
    if isinstance(values, list):
        cleaned = [profile_clean_value(item, clean_text) for item in values]
    elif isinstance(values, str):
        cleaned = [profile_clean_value(item, clean_text) for item in values.replace(";", ",").split(",")]
    else:
        cleaned = [profile_clean_value(values, clean_text)]
    return ", ".join(item for item in cleaned if item)


def local_media_items(post):
    media_items = post.get("media_items", [])
    if not isinstance(media_items, list):
        media_items = []
    if not media_items and post.get("media_url"):
        media_items = [{"url": post.get("media_url"), "type": post.get("media_type")}]

    result = []
    for media in media_items[:4]:
        if not isinstance(media, dict):
            continue
        url = str(media.get("url", ""))
        media_type = str(media.get("type", ""))
        if not url.startswith(("/media-files/", "/static/")):
            continue
        if media_type not in {"image", "video", "audio"}:
            continue
        result.append({"url": url, "type": media_type})
    return result


def build_profile_posts(posts, clean_text):
    result = []
    for post in posts if isinstance(posts, list) else []:
        if not isinstance(post, dict):
            continue
        hashtags = []
        for tag in post.get("hashtags", []) if isinstance(post.get("hashtags"), list) else []:
            cleaned = clean_text(tag).replace("#", "")[:80]
            if cleaned:
                hashtags.append(cleaned)
            if len(hashtags) == 8:
                break
        result.append({
            "id": clean_text(post.get("id", "")),
            "type": clean_text(post.get("type", "Публикация")),
            "text": clean_text(post.get("text", "")),
            "date": clean_text(post.get("date", post.get("created_at", ""))),
            "media": local_media_items(post),
            "hashtags": hashtags,
            "likes": list_count(post, "likes"),
            "comments": list_count(post, "comments"),
            "saves": list_count(post, "saves"),
        })
    return result


def build_profile_tabs(current_tab, counts):
    return [
        {"key": key, "count": int(counts.get(key, 0) or 0)}
        for key in ("all", "news", "projects", "media", "proof")
    ]


def build_profile_stats(counts, following_count, followers_count, show_activity):
    if not show_activity:
        return {"visible": False, "activity": 0, "following": 0, "followers": 0}
    return {
        "visible": True,
        "activity": int(counts.get("all", 0) or 0),
        "following": max(0, int(following_count or 0)),
        "followers": max(0, int(followers_count or 0)),
    }


def build_profile_header(user, clean_text):
    profession = profile_clean_value(getattr(user, "profession", ""), clean_text)
    country = profile_clean_value(getattr(user, "country", ""), clean_text)
    return {
        "meta": " · ".join(item for item in (profession, country) if item),
        "bio": profile_clean_value(getattr(user, "bio", ""), clean_text),
    }


def build_profile_info(user, clean_text, labels):
    fields = [
        ("age", getattr(user, "age", "")),
        ("languages", profile_list_text(getattr(user, "languages", []), clean_text)),
        ("goals", profile_list_text(getattr(user, "goals", []), clean_text)),
        ("interests", profile_list_text(getattr(user, "interests", []), clean_text)),
        ("skills", profile_list_text(getattr(user, "skills", []), clean_text)),
    ]
    return [
        {"label": labels[key], "value": profile_clean_value(value, clean_text)}
        for key, value in fields
        if profile_clean_value(value, clean_text)
    ]
