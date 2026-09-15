def _remember_allowed(cache, viewer_email, filename, allowed):
    if allowed:
        cache.remember_allowed(viewer_email, filename)
    return allowed


def can_access_media_file(filename, viewer_email, deps):
    filename = str(filename or "").strip()
    viewer_email = deps["normalize_email"](viewer_email)
    if not filename or not viewer_email:
        return False

    cache = deps["cache"]
    if cache.allows(viewer_email, filename):
        return True

    expected_url = f"/media-files/{filename}"
    if filename.startswith("chat_"):
        messages = deps["load_messages"]()
        for message in messages if isinstance(messages, list) else []:
            if not isinstance(message, dict) or str(message.get("media_url", "")).strip() != expected_url:
                continue
            participants = {
                deps["normalize_email"](message.get("from", "")),
                deps["normalize_email"](message.get("to", "")),
            }
            return _remember_allowed(cache, viewer_email, filename, viewer_email in participants)
        return False

    if filename.startswith("story_"):
        stories_data = deps["load_stories"]()
        stories = stories_data.get("stories", []) if isinstance(stories_data, dict) else []
        for story in stories if isinstance(stories, list) else []:
            if not isinstance(story, dict) or str(story.get("media_url", "")).strip() != expected_url:
                continue
            owner_email = deps["normalize_email"](story.get("email", ""))
            allowed = bool(owner_email and deps["can_view_user_stories"](viewer_email, owner_email))
            return _remember_allowed(cache, viewer_email, filename, allowed)
        return False

    if filename.startswith("post_"):
        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", []) if isinstance(feed_data, dict) else []
        for post in posts if isinstance(posts, list) else []:
            if not isinstance(post, dict):
                continue
            media_urls = {str(post.get("media_url", "")).strip()}
            media_items = post.get("media_items", [])
            if isinstance(media_items, list):
                media_urls.update(
                    str(item.get("url", "")).strip()
                    for item in media_items
                    if isinstance(item, dict)
                )
            if expected_url in media_urls:
                allowed = bool(deps["can_view_feed_post"](viewer_email, post))
                return _remember_allowed(cache, viewer_email, filename, allowed)
        return False

    # Avatars, news and legacy files are visible to authenticated users. Their
    # owning pages still enforce profile/news visibility before rendering URLs.
    return True
