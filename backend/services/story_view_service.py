def prepare_story_view(viewer, owner, stories_data, deps):
    viewer_email = deps["normalize_email"](getattr(viewer, "email", ""))
    owner_email = deps["normalize_email"](getattr(owner, "email", ""))

    if deps["is_blocked"](viewer.email, owner.email) or deps["is_blocked"](owner.email, viewer.email):
        deps["log_security_event"]("story_view_blocked", viewer.email, f"Blocked story view attempt to {owner.email}")
        return {
            "status": "blocked",
            "stories_data": stories_data,
            "owner_stories": [],
            "changed": False,
            "views_count": 0,
            "story_count_text": "",
        }

    if not deps["can_view_user_stories"](viewer.email, owner.email):
        return {
            "status": "restricted",
            "stories_data": stories_data,
            "owner_stories": [],
            "changed": False,
            "views_count": 0,
            "story_count_text": "",
        }

    stories_data = stories_data if isinstance(stories_data, dict) else {}
    stories = stories_data.get("stories", [])
    if not isinstance(stories, list):
        stories = []

    owner_stories = []
    changed = False

    for story in stories:
        if deps["normalize_email"](story.get("email", "")) != owner_email:
            continue

        if not deps["is_story_active"](story):
            continue

        views = story.get("views", [])
        if not isinstance(views, list):
            views = []

        normalized_views = [deps["normalize_email"](item) for item in views]
        if viewer_email != owner_email and viewer_email not in normalized_views:
            views.append(viewer.email)
            story["views"] = views
            changed = True

        owner_stories.append(story)

    owner_stories.sort(key=lambda item: item.get("created_at", ""))

    if not owner_stories:
        return {
            "status": "empty",
            "stories_data": stories_data,
            "owner_stories": [],
            "changed": changed,
            "views_count": 0,
            "story_count_text": "",
        }

    views_count = 0
    if owner_email == viewer_email:
        seen_viewers = set()
        for story in owner_stories:
            views = story.get("views", [])
            if not isinstance(views, list):
                continue

            for item in views:
                clean_viewer = deps["normalize_email"](item)
                if clean_viewer and clean_viewer != owner_email:
                    seen_viewers.add(clean_viewer)
        views_count = len(seen_viewers)

    story_count_text = f"{len(owner_stories)} историй"
    if owner_email == viewer_email:
        story_count_text += f" · {views_count} просмотров"

    stories_data["stories"] = stories

    return {
        "status": "ok",
        "stories_data": stories_data,
        "owner_stories": owner_stories,
        "changed": changed,
        "views_count": views_count,
        "story_count_text": story_count_text,
    }
