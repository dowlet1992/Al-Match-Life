from flask import Blueprint, jsonify, request


def create_feed_api(deps):
    feed_api = Blueprint("feed_api", __name__)

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

    def can_interact_with_post(current_user, post):
        author_email = deps["normalize_email"](post.get("email") or post.get("author_email") or "")
        if not author_email:
            return api_error("Post author not found", 400)

        if not deps["can_view_feed_post"](current_user.email, post):
            return api_error("Post interaction is not available", 403)

        return None

    def find_post(post_id):
        feed_data = deps["load_feed"]()
        posts, post = deps["feed_service"].find_post(feed_data, post_id)
        return feed_data, posts, post

    @feed_api.route("/api/feed")
    def api_feed():
        current_user, error = current_user_or_error()
        if error:
            return error

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        visible_posts = []

        for post in reversed(posts):
            if not isinstance(post, dict):
                continue

            if not deps["can_view_feed_post"](current_user.email, post):
                continue

            visible_posts.append(deps["api_post_payload"](post))

        return jsonify({
            "ok": True,
            "posts": visible_posts,
        })

    @feed_api.route("/api/feed/posts", methods=["POST"])
    def api_create_feed_post():
        current_user, error = current_user_or_error()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        text = deps["clean_text"](data.get("text", "")).strip()
        location = deps["clean_text"](data.get("location", "")).strip()
        post_type = deps["clean_text"](data.get("type", "Идея")).strip() or "Идея"
        hashtags = deps["parse_short_list"](data.get("hashtags", []), limit=10)
        content_language = deps["normalize_content_language_code"](data.get("language", ""))

        if not text:
            return api_error("Post text is required", 400)

        if content_language == "unknown":
            content_language = deps["detect_content_language"](" ".join([post_type, text, location, " ".join(hashtags)]))

        feed_data = deps["load_feed"]()
        new_post = deps["feed_service"].create_text_post(
            current_user,
            text,
            post_type=post_type,
            location=location,
            hashtags=hashtags,
            language=content_language,
        )
        deps["feed_service"].append_post(feed_data, new_post)
        deps["save_feed"](feed_data)
        deps["record_ai_feed_signal"](current_user.email, new_post, "create_post")

        return jsonify({
            "ok": True,
            "post": deps["api_post_payload"](new_post),
        }), 201

    @feed_api.route("/api/feed/posts/<post_id>/like", methods=["POST"])
    def api_like_feed_post(post_id):
        current_user, error = current_user_or_error()
        if error:
            return error

        feed_data, posts, post = find_post(post_id)
        if post is None:
            return api_error("Post not found", 404)

        interaction_error = can_interact_with_post(current_user, post)
        if interaction_error:
            return interaction_error

        liked = deps["feed_service"].toggle_list_value(post, "likes", current_user.email)
        feed_data["posts"] = posts
        deps["save_feed"](feed_data)
        deps["record_ai_feed_signal"](current_user.email, post, "like_post")

        return jsonify({
            "ok": True,
            "liked": liked,
            "post": deps["api_post_payload"](post),
        })

    @feed_api.route("/api/feed/posts/<post_id>/comment", methods=["POST"])
    def api_comment_feed_post(post_id):
        current_user, error = current_user_or_error()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        comment_text = deps["clean_text"](data.get("text", "")).strip()
        if not comment_text:
            return api_error("Comment text is required", 400)

        feed_data, posts, post = find_post(post_id)
        if post is None:
            return api_error("Post not found", 404)

        interaction_error = can_interact_with_post(current_user, post)
        if interaction_error:
            return interaction_error

        new_comment = deps["feed_service"].add_comment(post, current_user.email, current_user.name, comment_text)
        feed_data["posts"] = posts
        deps["save_feed"](feed_data)
        deps["record_ai_feed_signal"](current_user.email, post, "comment_post")

        return jsonify({
            "ok": True,
            "comment": new_comment,
            "post": deps["api_post_payload"](post),
        }), 201

    @feed_api.route("/api/feed/posts/<post_id>/save", methods=["POST"])
    def api_save_feed_post(post_id):
        current_user, error = current_user_or_error()
        if error:
            return error

        feed_data, posts, post = find_post(post_id)
        if post is None:
            return api_error("Post not found", 404)

        interaction_error = can_interact_with_post(current_user, post)
        if interaction_error:
            return interaction_error

        saved = deps["feed_service"].toggle_list_value(post, "saves", current_user.email)
        feed_data["posts"] = posts
        deps["save_feed"](feed_data)
        deps["record_ai_feed_signal"](current_user.email, post, "save_post")

        return jsonify({
            "ok": True,
            "saved": saved,
            "post": deps["api_post_payload"](post),
        })

    return feed_api
