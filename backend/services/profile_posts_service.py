ALLOWED_PROFILE_TABS = {"all", "news", "projects", "media", "proof"}


def normalize_profile_tab(tab_name, clean_text):
    tab_name = clean_text(tab_name or "").strip()
    if tab_name not in ALLOWED_PROFILE_TABS:
        return "all"
    return tab_name


def post_author_email(post, normalize_email):
    return normalize_email(post.get("email", post.get("author_email", "")))


def profile_post_matches_tab(post, tab_name, clean_text):
    post_type = clean_text(post.get("type", "")).lower()
    media_items = post.get("media_items", [])
    has_media = bool(post.get("media_url")) or (isinstance(media_items, list) and len(media_items) > 0)

    if tab_name == "all":
        return True
    if tab_name == "news":
        return "нов" in post_type or "news" in post_type or "идея" in post_type or "мысл" in post_type
    if tab_name == "projects":
        return "проект" in post_type or "project" in post_type or "partner" in post_type or "партн" in post_type
    if tab_name == "media":
        return has_media
    if tab_name == "proof":
        return "proof" in post_type or "доказ" in post_type
    return True


def profile_posts_for_user(posts, user_email, normalize_email):
    posts = posts if isinstance(posts, list) else []
    user_email = normalize_email(user_email)
    return [post for post in posts if post_author_email(post, normalize_email) == user_email]


def profile_post_summary(posts, user_email, requested_tab, deps):
    current_tab = normalize_profile_tab(requested_tab, deps["clean_text"])
    user_posts = profile_posts_for_user(posts, user_email, deps["normalize_email"])

    counts = {
        "all": len(user_posts),
        "news": len([post for post in user_posts if profile_post_matches_tab(post, "news", deps["clean_text"])]),
        "projects": len([post for post in user_posts if profile_post_matches_tab(post, "projects", deps["clean_text"])]),
        "media": len([post for post in user_posts if profile_post_matches_tab(post, "media", deps["clean_text"])]),
        "proof": len([post for post in user_posts if profile_post_matches_tab(post, "proof", deps["clean_text"])]),
    }
    filtered_posts = [
        post for post in reversed(user_posts)
        if profile_post_matches_tab(post, current_tab, deps["clean_text"])
    ]

    return {
        "current_tab": current_tab,
        "user_posts": user_posts,
        "filtered_posts": filtered_posts,
        "counts": counts,
    }
