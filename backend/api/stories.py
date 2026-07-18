from flask import Blueprint, jsonify


def create_stories_api(deps):
    stories_api = Blueprint("stories_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    def current_user_or_error():
        user = deps["get_api_current_user"]()
        if user is None:
            return None, api_error("Authentication required", 401)
        return user, None

    def story_payload(story):
        return {
            "id": story.get("id"),
            "email": deps["normalize_email"](story.get("email", "")),
            "media_url": deps["clean_text"](story.get("media_url", "")),
            "media_type": deps["clean_text"](story.get("media_type", "")),
            "created_at": deps["clean_text"](story.get("created_at", "")),
        }

    def active_stories_for_owner(owner_email):
        stories_data = deps["load_stories"]()
        stories = stories_data.get("stories", []) if isinstance(stories_data, dict) else []
        if not isinstance(stories, list):
            return stories_data, []

        owner_email = deps["normalize_email"](owner_email)
        owner_stories = [
            story for story in stories
            if isinstance(story, dict)
            and deps["normalize_email"](story.get("email", "")) == owner_email
            and deps["is_story_active"](story)
        ]
        owner_stories.sort(key=lambda story: story.get("created_at", ""))
        return stories_data, owner_stories

    @stories_api.route("/api/stories")
    def api_story_tray():
        current_user, error = current_user_or_error()
        if error:
            return error

        stories_data = deps["load_stories"]()
        stories = stories_data.get("stories", []) if isinstance(stories_data, dict) else []
        if not isinstance(stories, list):
            stories = []

        owners = {}
        for story in stories:
            if not isinstance(story, dict) or not deps["is_story_active"](story):
                continue

            owner_email = deps["normalize_email"](story.get("email", ""))
            if not owner_email or not deps["can_view_user_stories"](current_user.email, owner_email):
                continue

            owner = deps["find_user_by_email"](owner_email)
            if owner is None:
                continue

            entry = owners.setdefault(owner_email, {
                "user": deps["api_user_payload"](owner),
                "count": 0,
                "latest_created_at": "",
            })
            entry["count"] += 1
            if story.get("created_at", "") > entry["latest_created_at"]:
                entry["latest_created_at"] = deps["clean_text"](story.get("created_at", ""))

        return jsonify({
            "ok": True,
            "stories": sorted(
                owners.values(),
                key=lambda item: item.get("latest_created_at", ""),
                reverse=True,
            ),
        })

    @stories_api.route("/api/stories/<path:owner_email>")
    def api_owner_stories(owner_email):
        current_user, error = current_user_or_error()
        if error:
            return error

        owner = deps["find_user_by_email"](owner_email)
        if owner is None:
            return api_error("User not found", 404)

        if not deps["can_view_user_stories"](current_user.email, owner.email):
            return api_error("Stories are not available", 403)

        stories_data, owner_stories = active_stories_for_owner(owner.email)
        if not owner_stories:
            return jsonify({
                "ok": True,
                "user": deps["api_user_payload"](owner),
                "stories": [],
            })

        changed = False
        current_email = deps["normalize_email"](current_user.email)
        owner_clean_email = deps["normalize_email"](owner.email)
        if current_email != owner_clean_email:
            for story in owner_stories:
                views = story.get("views", [])
                if not isinstance(views, list):
                    views = []

                normalized_views = [deps["normalize_email"](item) for item in views]
                if current_email not in normalized_views:
                    views.append(current_user.email)
                    story["views"] = views
                    changed = True

        if changed:
            deps["save_stories"](stories_data)

        return jsonify({
            "ok": True,
            "user": deps["api_user_payload"](owner),
            "stories": [story_payload(story) for story in owner_stories],
        })

    return stories_api
