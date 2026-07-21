from flask import Blueprint


def create_profile_misc_routes(deps):
    profile_misc = Blueprint("profile_misc_routes", __name__)

    @profile_misc.route("/blocked/<email>")
    @deps["login_required"]
    def blocked_users_page(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        blocked_html = ""

        for blocked_email in deps["get_blocked_users"](user.email):
            blocked_user_obj = deps["find_user_by_email"](blocked_email)
            if blocked_user_obj is None:
                continue

            blocked_html += f"""
            <div style="background:#1e293b;padding:18px;border-radius:22px;margin-bottom:14px;display:flex;align-items:center;gap:16px;box-shadow:0 12px 28px rgba(0,0,0,0.18);">
                <img src="{deps["get_avatar_url"](blocked_user_obj.email)}" style="width:62px;height:62px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">
                <div style="flex:1;min-width:0;">
                    <div style="font-size:18px;font-weight:bold;margin-bottom:4px;">{deps["safe_text"](blocked_user_obj.name)}</div>
                    <div style="color:#94a3b8;font-size:14px;">{deps["safe_text"](blocked_user_obj.email)}</div>
                </div>
                <form method="POST" action="/unblock_user/{deps["safe_text"](user.email)}/{deps["safe_text"](blocked_user_obj.email)}">
                    {deps["csrf_input"]()}
                    <button type="submit" style="background:#16a34a;color:white;border:0;padding:10px 14px;border-radius:13px;font-weight:bold;cursor:pointer;">Разблокировать</button>
                </form>
            </div>
            """

        if blocked_html == "":
            blocked_html = """
            <div style="background:#1e293b;padding:28px;border-radius:24px;color:#cbd5e1;text-align:center;">
                Чёрный список пуст.
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head><meta charset="UTF-8"><title>Заблокированные</title></head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
            <div style="max-width:900px;margin:auto;">
                <a href="/settings/{deps["safe_text"](user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Настройки</a>
                <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:30px;border-radius:28px;margin-bottom:22px;box-shadow:0 18px 45px rgba(0,0,0,0.24);">
                    <h1 style="margin:0 0 8px 0;">🚫 Заблокированные</h1>
                    <p style="color:#cbd5e1;margin:0;">Здесь находятся пользователи, которых вы заблокировали.</p>
                </div>
                {blocked_html}
            </div>
        </body>
        </html>
        """

    @profile_misc.route("/hashtag/<email>/<tag>")
    @deps["login_required"]
    def hashtag_page(email, tag):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        posts = posts if isinstance(posts, list) else []
        tag_lower = str(tag or "").lower()
        results_html = ""

        for post in reversed(posts):
            post_tags = [str(item).lower() for item in post.get("hashtags", [])]
            if tag_lower not in post_tags:
                continue

            author = deps["find_user_by_email"](post.get("email"))
            author_name = author.name if author else "Unknown user"

            results_html += f"""
            <div style="background:#1e293b;padding:20px;border-radius:22px;margin-bottom:16px;">
                <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:10px;">
                    <strong>👤 {deps["safe_text"](author_name)}</strong>
                    <span style="color:#94a3b8;font-size:14px;">{deps["safe_text"](post.get("date", ""))}</span>
                </div>
                <div style="color:#60a5fa;font-weight:bold;margin-bottom:8px;">#{deps["safe_text"](tag)}</div>
                <p style="line-height:1.5;">{deps["safe_text"](post.get("text", ""))}</p>
            </div>
            """

        if results_html == "":
            results_html = f"""
            <div style="background:#1e293b;padding:24px;border-radius:22px;color:#cbd5e1;">
                По хэштегу #{deps["safe_text"](tag)} пока нет публикаций.
            </div>
            """

        return f"""
        <html>
        <head><meta charset="UTF-8"><title>#{deps["safe_text"](tag)}</title></head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:32px;">
            <div style="max-width:860px;margin:auto;">
                <a href="/dashboard/{deps["safe_text"](email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>
                <div style="background:#1e293b;padding:28px;border-radius:26px;margin-bottom:20px;">
                    <h1 style="margin:0;"># {deps["safe_text"](tag)}</h1>
                    <p style="color:#cbd5e1;margin-bottom:0;">Публикации по выбранному хэштегу.</p>
                </div>
                {results_html}
            </div>
        </body>
        </html>
        """

    return profile_misc
