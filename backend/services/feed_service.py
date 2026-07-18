from datetime import datetime


def next_post_id(posts):
    numeric_ids = []
    for post in posts:
        try:
            numeric_ids.append(int(post.get("id", 0)))
        except Exception:
            continue

    return max(numeric_ids) + 1 if numeric_ids else 1


def create_text_post(user, text, post_type="Идея", location="", hashtags=None, language="unknown"):
    now_display = datetime.now().strftime("%d.%m.%Y %H:%M")
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": None,
        "email": user.email,
        "name": user.name,
        "author_email": user.email,
        "author_name": user.name,
        "type": post_type or "Идея",
        "content_kind": "main_feed_post",
        "text": text,
        "location": location or "",
        "hashtags": hashtags or [],
        "language": language or "unknown",
        "media_url": "",
        "media_type": "",
        "media_items": [],
        "date": now_display,
        "created_at": now_iso,
        "likes": [],
        "comments": [],
        "shares": [],
        "saves": [],
        "ai_score": 0,
        "ai_summary": "",
        "ai_reasons": [],
    }


def append_post(feed_data, post):
    posts = feed_data.get("posts", [])
    if not isinstance(posts, list):
        posts = []

    post["id"] = next_post_id(posts)
    posts.append(post)
    feed_data["posts"] = posts
    return post


def find_post(feed_data, post_id):
    posts = feed_data.get("posts", [])
    if not isinstance(posts, list):
        return [], None

    for post in posts:
        if str(post.get("id", "")).strip() == str(post_id).strip():
            return posts, post

    return posts, None


def toggle_list_value(post, field_name, value):
    values = post.get(field_name, [])
    if not isinstance(values, list):
        values = []

    if value in values:
        values.remove(value)
        active = False
    else:
        values.append(value)
        active = True

    post[field_name] = values
    return active


def add_comment(post, author_email, author_name, text):
    comments = post.get("comments", [])
    if not isinstance(comments, list):
        comments = []

    comment = {
        "author": author_email,
        "author_name": author_name,
        "text": text,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }

    comments.append(comment)
    post["comments"] = comments
    return comment
