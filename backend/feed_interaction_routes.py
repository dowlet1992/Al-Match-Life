from datetime import datetime

from flask import Blueprint, jsonify, redirect, render_template, request


def create_feed_interaction_routes(deps):
    feed_interactions = Blueprint("feed_interactions", __name__)

    def fetch_response(payload, fallback_url, status=200):
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": True, **payload}), status
        return redirect(fallback_url)

    def action_user(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return None
        current_email = deps["normalize_email"](deps["current_session_email"]())
        return user if current_email == deps["normalize_email"](user.email) else None

    @feed_interactions.route("/comment_post/<user_identifier>/<int:post_id>", methods=["POST"])
    @deps["login_required"]
    def comment_post(user_identifier, post_id):
        deps["validate_csrf_token"]()
        user = action_user(user_identifier)

        if user is None:
            return "User not found", 403
        email = user.email

        comment_text = deps["clean_text"](request.form.get("comment", ""))
        if not comment_text or len(comment_text) > 2000:
            return "Comment must contain between 1 and 2000 characters", 400

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        created_comment = None
        comments_count = 0
        for post in posts:
            if post.get("id") == post_id:
                post_owner_email = post.get("email", "")
                if post_owner_email and (
                    deps["is_blocked"](email, post_owner_email)
                    or deps["is_blocked"](post_owner_email, email)
                ):
                    deps["log_security_event"]("comment_blocked", email, f"Blocked comment attempt on post {post_id}")
                    return deps["simple_page"](
                        "🚫 Комментарий недоступен",
                        "Нельзя комментировать этот пост, потому что один из пользователей заблокировал другого.",
                        email,
                    )

                comments = post.get("comments", [])
                created_comment = {
                    "author": user.email,
                    "author_name": user.name,
                    "text": comment_text,
                    "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                }
                comments.append(created_comment)

                post["comments"] = comments
                comments_count = len(comments)
                deps["record_ai_feed_signal"](email, post, "comment_post")
                break

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        if created_comment is None:
            return "Post not found", 404
        return fetch_response(
            {"action": "comment", "post_id": post_id, "comment": created_comment, "comments_count": comments_count},
            f"/dashboard/{user.email}",
            201,
        )

    @feed_interactions.route("/like_post/<user_identifier>/<int:post_id>", methods=["POST"])
    @deps["login_required"]
    def like_post(user_identifier, post_id):
        deps["validate_csrf_token"]()
        user = action_user(user_identifier)

        if user is None:
            return "User not found", 403

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        liked = False
        likes_count = 0
        found = False
        for post in posts:
            if post.get("id") != post_id:
                continue
            found = True

            post_owner_email = deps["normalize_email"](post.get("email", ""))

            if not post_owner_email:
                return deps["simple_page"]("Лайк недоступен", "Автор публикации не найден.", user.email)

            if deps["is_blocked"](user.email, post_owner_email) or deps["is_blocked"](post_owner_email, user.email):
                return deps["simple_page"]("🚫 Лайк недоступен", "Нельзя ставить лайк этому посту.", user.email)

            if deps["is_restricted"](user.email, post_owner_email) or deps["is_restricted"](post_owner_email, user.email):
                return deps["simple_page"]("Лайк недоступен", "Связь с автором ограничена.", user.email)

            likes = post.get("likes", [])
            if not isinstance(likes, list):
                likes = []

            if user.email in likes:
                likes.remove(user.email)
            else:
                likes.append(user.email)

            post["likes"] = likes
            liked = user.email in likes
            likes_count = len(likes)
            deps["record_ai_feed_signal"](user.email, post, "like_post")
            break

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        if not found:
            return "Post not found", 404
        return fetch_response(
            {"action": "like", "post_id": post_id, "liked": liked, "likes_count": likes_count},
            f"/dashboard/{deps['safe_text'](user.email)}",
        )

    @feed_interactions.route("/save_post/<user_identifier>/<int:post_id>", methods=["POST"])
    @deps["login_required"]
    def save_post_route(user_identifier, post_id):
        deps["validate_csrf_token"]()
        user = action_user(user_identifier)
        if user is None:
            return "User not found", 403
        email = user.email
        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        saved = False
        saves_count = 0
        found = False
        for post in posts:
            if post.get("id") == post_id:
                found = True
                post_owner_email = post.get("email", "")
                if post_owner_email and (
                    deps["is_blocked"](email, post_owner_email)
                    or deps["is_blocked"](post_owner_email, email)
                ):
                    deps["log_security_event"]("save_blocked", email, f"Blocked save attempt on post {post_id}")
                    return deps["simple_page"](
                        "🚫 Сохранение недоступно",
                        "Нельзя сохранить этот пост, потому что один из пользователей заблокировал другого.",
                        email,
                    )

                saves = post.get("saves", [])

                if email in saves:
                    saves.remove(email)
                else:
                    saves.append(email)

                post["saves"] = saves
                saved = email in saves
                saves_count = len(saves)
                deps["record_ai_feed_signal"](email, post, "save_post")
                break

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        if not found:
            return "Post not found", 404
        return fetch_response(
            {"action": "save", "post_id": post_id, "saved": saved, "saves_count": saves_count},
            f"/dashboard/{email}",
        )

    @feed_interactions.route("/delete_post/<user_identifier>/<int:post_id>", methods=["POST"])
    @deps["login_required"]
    def delete_post(user_identifier, post_id):
        deps["validate_csrf_token"]()
        current_user = action_user(user_identifier)

        if current_user is None:
            return "User not found", 403

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        filtered_posts = []
        deleted = False

        for post in posts:
            if post.get("id") == post_id and deps["normalize_email"](post.get("email", post.get("author_email", ""))) == deps["normalize_email"](current_user.email):
                deleted = True
                deps["log_security_event"]("post_deleted", current_user.email, f"Deleted post {post_id}")
                continue

            filtered_posts.append(post)

        if not deleted:
            return deps["simple_page"]("Пост не найден", "Публикация не найдена или вы не являетесь её автором.", current_user.email)

        feed_data["posts"] = filtered_posts
        deps["save_feed"](feed_data)

        return fetch_response(
            {"action": "delete", "post_id": post_id, "deleted": True},
            f"/dashboard/{current_user.email}",
        )

    @feed_interactions.route("/report_post/<user_identifier>/<int:post_id>", methods=["POST"])
    @deps["login_required"]
    def report_post(user_identifier, post_id):
        deps["validate_csrf_token"]()
        current_user = action_user(user_identifier)

        if current_user is None:
            return "User not found", 403

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        reported = False
        already_reported = False

        for post in posts:
            if post.get("id") != post_id:
                continue

            reports = post.get("reports", [])
            if not isinstance(reports, list):
                reports = []

            already_reported = any(
                deps["normalize_email"](item.get("email", "")) == deps["normalize_email"](current_user.email)
                for item in reports if isinstance(item, dict)
            )
            if already_reported:
                reported = True
                break

            reports.append({
                "email": current_user.email,
                "reason": deps["clean_text"](request.form.get("reason", "spam")),
                "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
            })
            post["reports"] = reports
            reported = True
            deps["log_security_event"]("post_reported", current_user.email, f"Reported post {post_id}")
            break

        if not reported:
            return deps["simple_page"]("Пост не найден", "Публикация не найдена.", current_user.email)

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        return fetch_response(
            {"action": "report", "post_id": post_id, "reported": True, "already_reported": already_reported},
            f"/dashboard/{current_user.email}",
        )

    @feed_interactions.route("/author_info/<email>/<int:post_id>")
    @deps["login_required"]
    def author_info(email, post_id):
        current_user = deps["find_user_by_email"](email)

        if current_user is None:
            return "User not found"

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        selected_post = None

        for post in posts:
            if post.get("id") == post_id:
                selected_post = post
                break

        if selected_post is None:
            return deps["simple_page"]("Пост не найден", "Публикация не найдена.", current_user.email)

        author_email = deps["normalize_email"](selected_post.get("email") or selected_post.get("author_email") or "")
        if author_email and (
            deps["is_blocked"](current_user.email, author_email)
            or deps["is_blocked"](author_email, current_user.email)
        ):
            deps["log_security_event"]("author_info_blocked", current_user.email, f"Blocked author view attempt {post_id}")
            return deps["simple_page"](
                "🚫 Автор недоступен",
                "Нельзя открыть информацию об авторе из-за настроек блокировки.",
                current_user.email,
            )

        author_user = deps["find_user_by_email"](author_email)
        author_name = author_user.name if author_user else "Пользователь"
        author_profession = author_user.profession if author_user else ""
        author_country = author_user.country if author_user else ""
        author_bio = author_user.bio if author_user else ""
        author_trust_score = getattr(author_user, "trust_score", 0) if author_user else 0

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        return render_template(
            "author_info.html",
            email=current_user.email,
            author={
                "name": author_name,
                "profession": author_profession,
                "country": author_country,
                "bio": author_bio,
                "trust_score": author_trust_score,
            },
            selected_post=selected_post,
            ui=ui,
        )

    @feed_interactions.route("/post_comments/<email>/<int:post_id>")
    @deps["login_required"]
    def post_comments(email, post_id):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        current_post = None
        for post in posts:
            if post.get("id") == post_id:
                current_post = post
                break

        if current_post is None:
            return "Post not found"

        post_owner_email = current_post.get("email", "")
        if post_owner_email and (
            deps["is_blocked"](email, post_owner_email)
            or deps["is_blocked"](post_owner_email, email)
        ):
            deps["log_security_event"]("post_comments_blocked", email, f"Blocked comments view attempt {post_id}")
            return deps["simple_page"](
                "🚫 Комментарии недоступны",
                "Нельзя открыть комментарии, потому что один из пользователей заблокировал другого.",
                email,
            )

        author = deps["find_user_by_email"](post_owner_email)
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        return render_template(
            "post_detail.html",
            email=user.email,
            post_id=post_id,
            author_name=author.name if author else "Unknown user",
            selected_post=current_post,
            comments=current_post.get("comments", []),
            ui=ui,
            csrf_token_input=deps["csrf_input"](),
        )

    @feed_interactions.route("/post/<email>/<int:post_id>")
    @deps["login_required"]
    def post_page(email, post_id):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        selected_post = None
        for post in posts:
            if post.get("id") == post_id:
                selected_post = post
                break

        if selected_post is None:
            return "Post not found"

        deps["record_ai_feed_signal"](email, selected_post, "open_post")

        post_owner_email = selected_post.get("email", "")
        if post_owner_email and (
            deps["is_blocked"](email, post_owner_email)
            or deps["is_blocked"](post_owner_email, email)
        ):
            deps["log_security_event"]("post_view_blocked", email, f"Blocked post view attempt {post_id}")
            return deps["simple_page"](
                "🚫 Пост недоступен",
                "Нельзя открыть этот пост, потому что один из пользователей заблокировал другого.",
                email,
            )

        author = deps["find_user_by_email"](selected_post.get("email"))
        author_name = author.name if author else "Unknown user"

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        return render_template(
            "post_detail.html",
            email=user.email,
            post_id=post_id,
            author_name=author_name,
            selected_post=selected_post,
            comments=selected_post.get("comments", []),
            ui=ui,
            csrf_token_input=deps["csrf_input"](),
        )

    @feed_interactions.route("/share_post/<email>/<int:post_id>")
    @deps["login_required"]
    def share_post(email, post_id):
        current_user = deps["find_user_by_email"](email)

        if current_user is None:
            return "User not found"

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        selected_post = None
        for post in posts:
            if post.get("id") == post_id:
                selected_post = post
                break

        if selected_post is None:
            return "Post not found"

        friends = []

        for friend_email in deps["get_friends"](email):
            friend = deps["find_user_by_email"](friend_email)

            if friend is None:
                continue
            if deps["is_blocked"](current_user.email, friend.email) or deps["is_blocked"](friend.email, current_user.email):
                continue
            friends.append({
                "email": friend.email,
                "name": friend.name,
                "profession": friend.profession,
                "avatar_url": deps["get_avatar_url"](friend.email),
            })

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        return render_template(
            "share_post.html",
            email=current_user.email,
            post_id=post_id,
            selected_post=selected_post,
            friends=friends,
            ui=ui,
            csrf_token_input=deps["csrf_input"](),
        )

    @feed_interactions.route("/send_shared_post/<email>/<int:post_id>/<receiver_email>", methods=["POST"])
    @deps["login_required"]
    def send_shared_post(email, post_id, receiver_email):
        deps["validate_csrf_token"]()
        sender = deps["find_user_by_email"](email)
        receiver = deps["find_user_by_email"](receiver_email)

        if sender is None or receiver is None:
            return "User not found"

        share_message = deps["clean_text"](request.form.get("message", ""))
        if len(share_message) > 1000:
            return "Message must not exceed 1000 characters", 400

        if deps["is_blocked"](sender.email, receiver.email) or deps["is_blocked"](receiver.email, sender.email):
            deps["log_security_event"]("share_blocked", sender.email, f"Blocked share attempt to {receiver.email}")
            return deps["simple_page"](
                "🚫 Отправка недоступна",
                "Нельзя отправить пост этому пользователю, потому что один из пользователей заблокировал другого.",
                sender.email,
            )

        if not deps["are_friends"](sender.email, receiver.email):
            deps["log_security_event"]("share_denied", sender.email, f"Attempted to share post to non-friend {receiver.email}")
            return deps["simple_page"](
                "🔒 Доступ закрыт",
                "Пост можно отправить только пользователю из списка друзей.",
                sender.email,
            )

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        selected_post = None
        for post in posts:
            if post.get("id") == post_id:
                selected_post = post
                shares = post.get("shares")
                if not isinstance(shares, list):
                    shares = []
                shares.append({
                    "email": email,
                    "to": receiver_email,
                    "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                })
                post["shares"] = shares
                deps["record_ai_feed_signal"](sender.email, post, "share_post")
                break

        if selected_post is None:
            return "Post not found"

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        message_text = deps["clean_text"](f"{sender.name} поделился постом: {selected_post.get('text', '')}")
        if share_message:
            message_text = f"{message_text}\n\n{share_message}"

        messages = deps["load_messages"]()
        messages.append({
            "from": sender.email,
            "to": receiver.email,
            "message": message_text,
            "shared_post_id": post_id,
            "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        })
        deps["save_messages"](messages)

        return redirect(f"/chat/{sender.email}/{receiver.email}")

    @feed_interactions.route("/translate_post/<email>/<post_id>", methods=["POST"])
    @deps["login_required"]
    def translate_post_page(email, post_id):
        deps["validate_csrf_token"]()
        current_user = deps["find_user_by_email"](email)

        if current_user is None:
            return "User not found"

        post = deps["find_post_by_id"](post_id)
        if post is None:
            return deps["simple_page"]("Пост не найден", "Публикация не найдена или была удалена.", current_user.email)

        author_email = deps["normalize_email"](post.get("email", ""))
        if deps["is_blocked"](current_user.email, author_email) or deps["is_blocked"](author_email, current_user.email):
            return deps["simple_page"]("Доступ закрыт", "Вы не можете открыть перевод этой публикации.", current_user.email)

        content_language = deps["normalize_content_language_code"](post.get("language", ""))
        if content_language == "unknown":
            content_language = deps["detect_content_language"](" ".join([
                str(post.get("type", "")),
                str(post.get("text", "")),
                str(post.get("location", "")),
                " ".join(post.get("hashtags", [])),
            ]))

        target_language = deps["normalize_content_language_code"](deps["get_current_language"](current_user))
        if target_language == "unknown":
            target_language = deps["default_language"]()

        deps["record_ai_feed_signal"](current_user.email, post, "translate_post")

        source_text = post.get("text", "")
        cache_key = f"{content_language}->{target_language}"
        translation_cache = post.get("ai_translations", {})
        cached_translation = translation_cache.get(cache_key, {}) if isinstance(translation_cache, dict) else {}

        if cached_translation.get("source_text") == source_text and cached_translation.get("result"):
            translated_text = cached_translation.get("result", "")
            translation_cache_status = "Готовый AI-перевод загружен из кэша."
        else:
            translated_text = deps["generate_ai_translation_summary"](source_text, content_language, target_language)
            translation_cache_status = "AI-перевод создан и сохранён."

            try:
                feed_data = deps["load_feed"]()
                for saved_post in feed_data.get("posts", []):
                    if str(saved_post.get("id", "")).strip() == str(post_id).strip():
                        saved_cache = saved_post.get("ai_translations", {})
                        if not isinstance(saved_cache, dict):
                            saved_cache = {}

                        saved_cache[cache_key] = {
                            "source_text": source_text,
                            "result": translated_text,
                            "source_language": content_language,
                            "target_language": target_language,
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        saved_post["ai_translations"] = saved_cache
                        break

                deps["save_feed"](feed_data)
            except Exception as error:
                deps["log_security_event"]("ai_translation_cache_failed", current_user.email, str(error))
                translation_cache_status = "AI-перевод создан, но кэш сохранить не удалось."

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        language_names = deps["content_languages"]()
        return render_template(
            "post_translation.html",
            email=current_user.email,
            source_language_name=language_names.get(content_language, content_language),
            target_language_name=language_names.get(target_language, target_language),
            source_text=post.get("text", ""),
            translated_text=translated_text,
            cache_status=translation_cache_status,
            ui=ui,
        )

    return feed_interactions
