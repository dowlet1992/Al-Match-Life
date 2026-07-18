from datetime import datetime

from flask import Blueprint, redirect, request


def create_feed_interaction_routes(deps):
    feed_interactions = Blueprint("feed_interactions", __name__)

    @feed_interactions.route("/comment_post/<email>/<int:post_id>", methods=["POST"])
    @deps["login_required"]
    def comment_post(email, post_id):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        comment_text = deps["clean_text"](request.form["comment"])

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

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
                comments.append({
                    "author": user.email,
                    "author_name": user.name,
                    "text": comment_text,
                    "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                })

                post["comments"] = comments
                deps["record_ai_feed_signal"](email, post, "comment_post")
                break

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        return redirect(f"/dashboard/{user.email}")

    @feed_interactions.route("/like_post/<email>/<int:post_id>")
    @deps["login_required"]
    def like_post(email, post_id):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        for post in posts:
            if post.get("id") != post_id:
                continue

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
            deps["record_ai_feed_signal"](user.email, post, "like_post")
            break

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        return redirect(f"/dashboard/{deps['safe_text'](user.email)}")

    @feed_interactions.route("/save_post/<email>/<int:post_id>")
    @deps["login_required"]
    def save_post_route(email, post_id):
        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])

        for post in posts:
            if post.get("id") == post_id:
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
                deps["record_ai_feed_signal"](email, post, "save_post")
                break

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        return redirect(f"/dashboard/{email}")

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

        comments_html = ""
        for comment in current_post.get("comments", []):
            comments_html += f"""
            <div style="background:#1e293b;padding:16px;border-radius:16px;margin-bottom:12px;">
                <strong>{deps["safe_text"](comment.get('author_name','User'))}</strong><br>
                <span style="color:#cbd5e1;">{deps["safe_text"](comment.get('text',''))}</span><br>
                <small style="color:#94a3b8;">{deps["safe_text"](comment.get('date',''))}</small>
            </div>
            """

        return f"""
        <html>
        <head>
            <title>Комментарии</title>
        </head>

        <body style="background:#0f172a;color:white;font-family:Arial;padding:30px;max-width:900px;margin:auto;">

            <a href="/dashboard/{deps["safe_text"](email)}" style="color:white;">← Назад</a>

            <h1>💬 Комментарии</h1>

            <div style="background:#1e293b;padding:20px;border-radius:20px;margin-bottom:20px;">
                <h3>{deps["safe_text"](current_post.get('type','Публикация'))}</h3>
                <p>{deps["safe_text"](current_post.get('text',''))}</p>
            </div>

            <form method="POST" action="/comment_post/{email}/{post_id}">
                {deps["csrf_input"]()}
                <textarea
                    name="comment"
                    required
                    placeholder="Написать комментарий..."
                    style="width:100%;height:100px;padding:12px;border-radius:12px;">
                </textarea>

                <br><br>

                <button type="submit">
                    Отправить комментарий
                </button>
            </form>

            <br>

            {comments_html}

        </body>
        </html>
        """

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

        comments_html = ""
        for comment in selected_post.get("comments", []):
            comments_html += f"""
            <div style="background:#1e293b;padding:14px;border-radius:14px;margin-top:10px;">
                <strong>{deps["safe_text"](comment.get("author_name", "User"))}</strong>
                <p>{deps["safe_text"](comment.get("text", ""))}</p>
                <small style="color:#94a3b8;">{deps["safe_text"](comment.get("date", ""))}</small>
            </div>
            """

        if comments_html == "":
            comments_html = "<p style='color:#94a3b8;'>Пока нет комментариев.</p>"

        return f"""
        <html>
        <head>
        <meta charset="UTF-8">
        <title>Пост</title>
        <style>
        body{{background:#0f172a;color:white;font-family:Arial;padding:40px}}
        .container{{max-width:800px;margin:auto}}
        .card{{background:#0f172a;padding:24px;border-radius:24px;margin-bottom:20px}}
        .box{{background:#1e293b;padding:24px;border-radius:24px;margin-bottom:20px}}
        textarea{{width:100%;height:100px;padding:14px;border:none;border-radius:14px;background:#1e293b;color:white;resize:none}}
        button{{background:#2563eb;color:white;border:none;border-radius:14px;padding:12px 18px;font-weight:bold;margin-top:10px;cursor:pointer}}
        a{{color:white;text-decoration:none}}
        </style>
        </head>
        <body>
        <div class="container">
            <p><a href="/dashboard/{deps["safe_text"](email)}">← Назад</a></p>

            <div class="box">
                <h2>👤 {deps["safe_text"](author_name)}</h2>
                <p style="color:#60a5fa;font-weight:bold;">{deps["safe_text"](selected_post.get("type", "Публикация"))}</p>
                <p style="font-size:18px;line-height:1.5;">{deps["safe_text"](selected_post.get("text", ""))}</p>
                <small style="color:#94a3b8;">{deps["safe_text"](selected_post.get("date", ""))}</small>
            </div>

            <div class="box">
                <h2>💬 Комментарии</h2>

                {comments_html}

                <form method="POST" action="/comment_post/{email}/{post_id}">
                    {deps["csrf_input"]()}
                    <textarea name="comment" placeholder="Написать комментарий..." required></textarea>
                    <button type="submit">Отправить</button>
                </form>
            </div>
        </div>
        </body>
        </html>
        """

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

        friend_emails = deps["get_friends"](email)
        people_html = ""

        for friend_email in friend_emails:
            friend = deps["find_user_by_email"](friend_email)

            if friend is None:
                continue

            avatar_url = deps["get_avatar_url"](friend.email)

            people_html += f"""
            <div style="background:#1e293b;padding:16px;border-radius:20px;margin-bottom:12px;display:flex;align-items:center;gap:14px;">
                <img src="{avatar_url}" style="width:56px;height:56px;border-radius:50%;object-fit:cover;background:#334155;">

                <div style="flex:1;">
                    <div style="font-weight:bold;font-size:18px;">{deps["safe_text"](friend.name)}</div>
                    <div style="color:#94a3b8;font-size:14px;">{deps["safe_text"](friend.profession)}</div>
                </div>

                <a href="/send_shared_post/{email}/{post_id}/{friend.email}" style="background:#2563eb;color:white;text-decoration:none;padding:11px 15px;border-radius:14px;font-weight:bold;">
                    Отправить
                </a>
            </div>
            """

        if people_html == "":
            people_html = """
            <div style="background:#1e293b;padding:24px;border-radius:20px;color:#cbd5e1;text-align:center;">
                Пока нет друзей для отправки поста.
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <title>Поделиться постом</title>
        </head>

        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
            <div style="max-width:760px;margin:auto;">

                <a href="/dashboard/{email}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">
                    ← Назад
                </a>

                <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:20px;">
                    <h1 style="margin:0 0 8px 0;">📤 Поделиться постом</h1>
                    <p style="color:#cbd5e1;margin:0;">Выберите друга, которому хотите отправить публикацию.</p>
                </div>

                <div style="background:#0f172a;padding:18px;border-radius:22px;margin-bottom:20px;border:1px solid #334155;">
                    <div style="color:#60a5fa;font-weight:bold;margin-bottom:8px;">{deps["safe_text"](selected_post.get('type', 'Публикация'))}</div>
                    <div style="color:#e5e7eb;line-height:1.5;">{deps["safe_text"](selected_post.get('text', ''))}</div>
                </div>

                {people_html}

            </div>
        </body>
        </html>
        """

    @feed_interactions.route("/send_shared_post/<email>/<int:post_id>/<receiver_email>")
    @deps["login_required"]
    def send_shared_post(email, post_id, receiver_email):
        sender = deps["find_user_by_email"](email)
        receiver = deps["find_user_by_email"](receiver_email)

        if sender is None or receiver is None:
            return "User not found"

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
                shares = post.get("shares", [])
                shares.append({
                    "email": email,
                    "to": receiver_email,
                    "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
                })
                post["shares"] = shares
                break

        if selected_post is None:
            return "Post not found"

        feed_data["posts"] = posts
        deps["save_feed"](feed_data)

        messages = deps["load_messages"]()
        messages.append({
            "from": sender.email,
            "to": receiver.email,
            "message": deps["clean_text"](f"{sender.name} поделился постом: {selected_post.get('text', '')}"),
            "shared_post_id": post_id,
            "time": datetime.now().strftime("%d.%m.%Y %H:%M"),
        })
        deps["save_messages"](messages)

        return redirect(f"/chat/{sender.email}/{receiver.email}")

    @feed_interactions.route("/translate_post/<email>/<post_id>")
    @deps["login_required"]
    def translate_post_page(email, post_id):
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

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AI перевод - AI Match Life</title>
        </head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
            <div style="max-width:880px;margin:auto;">
                <a href="/feed/{deps["safe_text"](current_user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад в AI Discover</a>

                <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:28px;border-radius:28px;margin-bottom:18px;border:1px solid rgba(148,163,184,0.14);">
                    <h1 style="margin:0 0 10px 0;">🌍 AI перевод</h1>
                    <p style="margin:0;color:#cbd5e1;line-height:1.55;">AI помогает понять полезный контент, даже если он опубликован на другом языке.</p>
                </div>

                <div style="background:#1e293b;border-radius:24px;padding:22px;margin-bottom:18px;">
                    <h2 style="margin:0 0 12px 0;color:#93c5fd;">Оригинал · {deps["safe_text"](deps["content_languages"]().get(content_language, content_language))}</h2>
                    <p style="white-space:pre-wrap;line-height:1.6;color:#e5e7eb;">{deps["safe_text"](post.get("text", ""))}</p>
                </div>

                <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.22);border-radius:24px;padding:22px;">
                    <h2 style="margin:0 0 12px 0;color:#bfdbfe;">AI результат · {deps["safe_text"](deps["content_languages"]().get(target_language, target_language))}</h2>
                    <p style="margin:0 0 12px 0;color:#94a3b8;font-size:14px;">{deps["safe_text"](translation_cache_status)}</p>
                    <p style="white-space:pre-wrap;line-height:1.6;color:#dbeafe;">{deps["safe_text"](translated_text)}</p>
                </div>
            </div>
        </body>
        </html>
        """

    return feed_interactions
