from flask import Blueprint, render_template, request


def create_dashboard_routes(deps):
    routes = Blueprint("dashboard_routes", __name__)

    @routes.route("/dashboard/<identifier>")
    @deps["login_required"]
    def dashboard(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("dashboard_owner_mismatch", deps["current_session_email"](), "Dashboard identifier did not match session")
            return "Forbidden", 403

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        settings = deps["normalize_user_ai_settings"](user.email)
        autoplay = settings.get("autoplay_video", True) is True
        video_status = ui.get("autoplay_video_short", "Автовидео") if autoplay else ui.get("tap_play", "Нажмите ▶")
        posts = deps["load_feed"]().get("posts", [])
        posts_html = ""
        visible_post_count = 0
        for post in reversed(posts if isinstance(posts, list) else []):
            if not deps["can_view_feed_post"](user.email, post):
                continue
            visible_post_count += 1
            author = deps["find_user_by_email"](post.get("email"))
            author_email = author.email if author else post.get("email", "")
            media_items = post.get("media_items", [])
            if not media_items and post.get("media_url"):
                media_items = [{"url": post.get("media_url", ""), "type": post.get("media_type", "")}]
            media_html = render_template(
                "dashboard_post_media.html", media_items=media_items, video_status=video_status,
                sound_label=ui.get("sound", "Sound"), audio_label=ui.get("audio_music", "Audio / music"),
            ) if media_items else ""
            post_view = {
                "id": post.get("id"), "author_name": author.name if author else ui.get("user", "User"),
                "author_email": author_email, "author_id": getattr(author, "id", "") if author else "",
                "author_avatar": deps["get_avatar_url"](author_email) if author_email else "/static/default-avatar.png",
                "date": post.get("date", ""), "type_label": deps["safe_text"](post.get("type", ui.get("publication", "Publication"))),
                "text": str(post.get("text", "")).strip(), "location": post.get("location", ""),
                "hashtags": post.get("hashtags", []), "likes_count": len(post.get("likes", [])),
                "comments_count": len(post.get("comments", [])), "shares_count": len(post.get("shares", [])),
                "saves_count": len(post.get("saves", [])),
                "comments": [{"author_name": item.get("author_name", ui.get("user", "User")), "text": item.get("text", "")} for item in post.get("comments", []) if isinstance(item, dict)],
                "owned": deps["normalize_email"](author_email) == deps["normalize_email"](user.email),
            }
            posts_html += render_template(
                "dashboard_post_card.html", post=post_view, media_html=media_html,
                viewer_email=user.email, viewer_id=user.id, ui=ui, csrf_token_input=deps["csrf_input"](),
            )
        if not visible_post_count:
            posts_html = render_template("dashboard_posts_empty.html", ui=ui)

        story_views = []
        try:
            active = [story for story in deps["load_stories"]().get("stories", []) if deps["is_story_active"](story)]
            connected = set()
            for getter in deps["connection_getters"]:
                for email in getter(user.email):
                    normalized = deps["normalize_email"](email)
                    if normalized:
                        connected.add(normalized)
            connected.discard(deps["normalize_email"](user.email))
            seen = set()
            owners = []
            for story in reversed(active):
                story_email = deps["normalize_email"](story.get("email", ""))
                if not story_email or story_email in seen:
                    continue
                if story_email not in connected and not deps["can_view_user_stories"](user.email, story_email):
                    continue
                owner = deps["find_user_by_email"](story_email)
                if owner is None or not deps["can_view_user_stories"](user.email, owner.email):
                    continue
                seen.add(story_email)
                owners.append(owner)
                if len(owners) >= 12:
                    break
            story_views = [{"id": owner.id, "email": owner.email, "name": owner.name, "avatar_url": deps["get_avatar_url"](owner.email)} for owner in owners]
        except Exception as error:
            deps["log_security_event"]("dashboard_stories_failed", user.email, str(error))

        seen_matches = set()
        for match in deps["find_best_matches"](user):
            candidate = match.get("user") if isinstance(match, dict) else None
            candidate_email = deps["normalize_email"](getattr(candidate, "email", "")) if candidate else ""
            if candidate_email and candidate_email not in seen_matches and deps["can_show_user_in_ai_recommendations"](user.email, candidate):
                seen_matches.add(candidate_email)

        return render_template(
            "dashboard.html", name=deps["safe_text"](user.name), email=deps["safe_text"](user.email), user_id=user.id,
            trust_score=user.trust_score, posts=posts_html, feed_autoplay_enabled=autoplay,
            activity_count=deps["calculate_activity_count"](user, posts), stories=story_views,
            life_radar=deps["generate_life_radar"](user), translations=deps["get_translations"](request.headers.get("Accept-Language")),
            ui=ui, avatar_url=deps["get_avatar_url"](user.email), notifications_count=len(deps["get_notifications"](user.email)),
            matches_count=len(seen_matches), friends_count=deps["count_friends"](user.email),
            followers_count=deps["count_followers"](user.email), following_count=deps["count_following"](user.email),
            is_admin=deps["is_admin"](user.email), csrf_token_input=deps["csrf_input"](),
        )

    return routes
