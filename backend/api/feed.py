import base64
import re

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

    def private_json(payload):
        response = jsonify(payload)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    def can_interact_with_post(current_user, post):
        author_email = deps["normalize_email"](post.get("email") or post.get("author_email") or "")
        if not author_email:
            return api_error("Post author not found", 400)

        if not deps["can_view_feed_post"](current_user.email, post):
            return api_error("Post interaction is not available", 403)

        return None

    def viewer_post_payload(post, current_user):
        payload = deps["api_post_payload"](post)
        payload["liked"] = current_user.email in (post.get("likes", []) or [])
        payload["saved"] = current_user.email in (post.get("saves", []) or [])
        return payload

    def find_post(post_id):
        feed_data = deps["load_feed"]()
        posts, post = deps["feed_service"].find_post(feed_data, post_id)
        return feed_data, posts, post

    def requested_page():
        try:
            limit = int(request.args.get("limit", "20"))
        except (TypeError, ValueError):
            return None, None, api_error("Invalid limit", 400)
        if limit < 1 or limit > 50:
            return None, None, api_error("Limit must be between 1 and 50", 400)
        cursor = deps["clean_text"](request.args.get("cursor", ""))
        if not cursor:
            return limit, "", None
        if len(cursor) > 512 or re.fullmatch(r"[A-Za-z0-9_-]+", cursor) is None:
            return None, None, api_error("Invalid cursor", 400)
        try:
            padding = "=" * (-len(cursor) % 4)
            post_id = base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode("utf-8")
        except (UnicodeError, ValueError):
            return None, None, api_error("Invalid cursor", 400)
        if (not post_id.isascii() or not post_id.isdigit() or len(post_id) > 20 or
                int(post_id) < 1 or str(int(post_id)) != post_id):
            return None, None, api_error("Invalid cursor", 400)
        return limit, post_id, None

    def encode_cursor(post_id):
        return base64.urlsafe_b64encode(post_id.encode("utf-8")).decode("ascii").rstrip("=")

    @feed_api.route("/api/feed")
    def api_feed():
        current_user, error = current_user_or_error()
        if error:
            return error

        limit, after_id, error = requested_page()
        if error:
            return error

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        visible_posts = []
        cursor_seen = not after_id

        for post in reversed(posts):
            if not isinstance(post, dict):
                continue

            if not deps["can_view_feed_post"](current_user.email, post):
                continue

            payload = viewer_post_payload(post, current_user)
            post_id = deps["clean_text"](payload.get("id", ""))
            if not cursor_seen:
                if post_id == after_id:
                    cursor_seen = True
                continue
            visible_posts.append(payload)
            if len(visible_posts) > limit:
                break

        if not cursor_seen:
            return api_error("Invalid cursor", 400)

        has_more = len(visible_posts) > limit
        page_posts = visible_posts[:limit]
        next_cursor = encode_cursor(str(page_posts[-1]["id"])) if has_more and page_posts else None

        return private_json({
            "ok": True,
            "posts": page_posts,
            "next_cursor": next_cursor,
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
            "post": viewer_post_payload(post, current_user),
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
        if len(comment_text) > 1000:
            return api_error("Comment text must not exceed 1000 characters", 400)

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
            "post": viewer_post_payload(post, current_user),
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
            "post": viewer_post_payload(post, current_user),
        })

    return feed_api
