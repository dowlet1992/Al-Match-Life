from datetime import datetime


def normalize_email(value):
    return str(value or "").strip().lower()


def clean_text(value):
    return str(value or "").strip()


def is_story_active(story, now=None):
    story = story if isinstance(story, dict) else {}
    now = now or datetime.now()
    try:
        created_at = datetime.strptime(story.get("created_at", ""), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return False

    hours_passed = (now - created_at).total_seconds() / 3600
    return hours_passed <= 24


def has_hidden_stories_from(viewer_email, target_email, hidden_stories_data):
    viewer_email = normalize_email(viewer_email)
    target_email = normalize_email(target_email)
    hidden_stories_data = hidden_stories_data if isinstance(hidden_stories_data, dict) else {}
    return target_email in hidden_stories_data.get("hidden_stories", {}).get(viewer_email, [])


def hide_stories_from_user(viewer_email, target_email, hidden_stories_data):
    viewer_email = normalize_email(viewer_email)
    target_email = normalize_email(target_email)
    hidden_stories_data = hidden_stories_data if isinstance(hidden_stories_data, dict) else {}
    if not viewer_email or not target_email or viewer_email == target_email:
        return hidden_stories_data, False

    hidden = hidden_stories_data.get("hidden_stories", {})
    hidden = hidden if isinstance(hidden, dict) else {}
    hidden_list = hidden.get(viewer_email, [])
    hidden_list = hidden_list if isinstance(hidden_list, list) else []
    if target_email not in hidden_list:
        hidden_list.append(target_email)
    hidden[viewer_email] = hidden_list
    hidden_stories_data["hidden_stories"] = hidden
    return hidden_stories_data, True


def show_stories_from_user(viewer_email, target_email, hidden_stories_data):
    viewer_email = normalize_email(viewer_email)
    target_email = normalize_email(target_email)
    hidden_stories_data = hidden_stories_data if isinstance(hidden_stories_data, dict) else {}
    hidden = hidden_stories_data.get("hidden_stories", {})
    hidden = hidden if isinstance(hidden, dict) else {}
    hidden_list = hidden.get(viewer_email, [])
    hidden_list = hidden_list if isinstance(hidden_list, list) else []
    if target_email in hidden_list:
        hidden_list.remove(target_email)
    hidden[viewer_email] = hidden_list
    hidden_stories_data["hidden_stories"] = hidden
    return hidden_stories_data, True


def can_view_user_stories(
    viewer_email,
    owner_email,
    owner_settings,
    hidden_stories_data,
    is_blocked,
    are_friends,
):
    viewer_email = normalize_email(viewer_email)
    owner_email = normalize_email(owner_email)

    if not viewer_email or not owner_email:
        return False

    if viewer_email == owner_email:
        return True

    if is_blocked(viewer_email, owner_email) or is_blocked(owner_email, viewer_email):
        return False

    if has_hidden_stories_from(viewer_email, owner_email, hidden_stories_data):
        return False

    owner_settings = owner_settings if isinstance(owner_settings, dict) else {}
    story_visibility = clean_text(owner_settings.get("story_visibility", "friends"))

    if story_visibility == "none":
        return False

    if story_visibility == "everyone":
        return True

    if story_visibility in {"friends", "close_friends"}:
        return are_friends(viewer_email, owner_email)

    return False
