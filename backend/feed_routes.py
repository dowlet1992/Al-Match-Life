from flask import Blueprint, redirect, render_template, request

from backend.services import feed_post_creation_service, feed_ranking_service


def _media_items(post):
    items = post.get("media_items", [])
    if not items and post.get("media_url"):
        items = [{
            "url": post.get("media_url", ""),
            "type": post.get("media_type", ""),
            "name": "media",
        }]
    return [
        {"url": item.get("url", ""), "type": item.get("type", "")}
        for item in items[:4]
        if item.get("url") and item.get("type") in {"image", "video", "audio"}
    ]


def create_feed_routes(deps):
    feed_routes = Blueprint("feed_routes", __name__)

    @feed_routes.route("/feed/<identifier>")
    @deps["login_required"]
    def feed_page(identifier):
        current_user = deps["find_user_by_identifier"](identifier)
        if current_user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](current_user.email):
            deps["log_security_event"]("feed_owner_mismatch", deps["current_session_email"](), f"target={current_user.email}")
            return "Forbidden", 403

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        ranking = feed_ranking_service.rank_feed_posts(current_user, posts, {
            "calculate_ai_learning_boost": lambda user_email, post, language: deps["calculate_ai_learning_boost"](
                user_email, post, language
            ),
            "can_view_feed_post": deps["can_view_feed_post"],
            "clean_text": deps["clean_text"],
            "content_languages": deps["content_languages"],
            "detect_content_language": deps["detect_content_language"],
            "find_user_by_email": deps["find_user_by_email"],
            "get_current_language": deps["get_current_language"],
            "get_user_language_signals": deps["get_user_language_signals"],
            "normalize_content_language_code": deps["normalize_content_language_code"],
            "normalize_email": deps["normalize_email"],
            "normalize_user_ai_settings": deps["normalize_user_ai_settings"],
            "score_language_match": deps["score_language_match"],
            "supported_languages": deps["supported_languages"],
        })
        if ranking["feed_changed"]:
            feed_data["posts"] = posts
            deps["save_feed"](feed_data)

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        current_email = deps["normalize_email"](current_user.email)
        content_languages = deps["content_languages"]()
        post_views = []

        for item in ranking["ranked_posts"]:
            post = item.get("post", {})
            author = item.get("author")
            author_email = deps["normalize_email"](author.email)
            content_language = deps["normalize_content_language_code"](
                item.get("content_language", post.get("language", "unknown"))
            )
            can_write = False
            if author_email != current_email:
                can_write, _, _ = deps["get_message_permission_status"](current_user, author)

            post_views.append({
                "id": post.get("id"),
                "author_id": author.id,
                "author_email": author.email,
                "author_name": author.name,
                "author_profession": author.profession,
                "avatar_url": deps["get_avatar_url"](author.email),
                "location": post.get("location", ""),
                "score": int(max(0, min(item.get("score", 0), 100))),
                "type": post.get("type", ui.get("post", "Post")),
                "text": post.get("text", ""),
                "content_language": content_language,
                "content_language_name": content_languages.get(content_language, "Unknown"),
                "media": _media_items(post),
                "hashtags": [
                    deps["clean_text"](tag).replace("#", "")
                    for tag in post.get("hashtags", [])[:8]
                    if deps["clean_text"](tag).replace("#", "")
                ],
                "ai_reasons": item.get("ai_reasons", []),
                "likes_count": len(post.get("likes", [])),
                "comments_count": len(post.get("comments", [])),
                "saves_count": len(post.get("saves", [])),
                "shares_count": len(post.get("shares", [])) if isinstance(post.get("shares", []), list) else 0,
                "is_owner": author_email == current_email,
                "can_write": can_write,
                "can_translate": (
                    content_language not in ranking["user_language_codes"]
                    and content_language != "unknown"
                ),
            })

        user_languages = ", ".join(ranking["user_language_names"]) or ui.get("auto_language", "Auto")
        feed_mode = (
            ui.get("ai_personalization_on", "AI personalization on")
            if ranking["ai_feed_enabled"]
            else ui.get("standard_feed", "Standard feed")
        )
        return render_template(
            "feed.html",
            ui=ui,
            email=current_user.email,
            posts=post_views,
            user_languages=user_languages,
            feed_mode=feed_mode,
            csrf_token_input=deps["csrf_input"](),
        )

    @feed_routes.route("/create_post/<identifier>", methods=["POST"])
    @deps["login_required"]
    def create_post(identifier):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("feed_create_owner_mismatch", deps["current_session_email"](), f"target={user.email}")
            return "Forbidden", 403

        result = feed_post_creation_service.build_web_post(
            user,
            request.form,
            request.files.getlist("media"),
            deps["load_feed"](),
            {
                "allowed_mime_type": deps["allowed_mime_type"],
                "clean_text": deps["clean_text"],
                "detect_content_language": deps["detect_content_language"],
                "log_security_event": deps["log_security_event"],
                "normalize_content_language_code": deps["normalize_content_language_code"],
                "upload_folder": deps["upload_folder"]() if callable(deps["upload_folder"]) else deps["upload_folder"],
            },
        )
        if not result.get("ok"):
            ui = deps["translation_bundle"](deps["get_current_language"](user))
            return deps["simple_page"](
                ui.get("empty_post_title", "Empty post"),
                ui.get("empty_post_intro", "Add text, photo, video, or audio before publishing."),
                user.email,
            )

        deps["save_feed"](result["feed_data"])
        deps["record_ai_feed_signal"](user.email, result["post"], "create_post")
        return_to = deps["clean_text"](request.form.get("return_to", ""))
        referer = request.headers.get("Referer", "")
        if return_to == "dashboard" or f"/dashboard/{user.email}" in referer:
            return redirect(f"/dashboard/{user.email}")
        return redirect(f"/feed/{user.email}")

    return feed_routes
