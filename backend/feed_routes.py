from flask import Blueprint, redirect, request

from backend.services import feed_ranking_service
from backend.services import feed_post_creation_service


def create_feed_routes(deps):
    feed_routes = Blueprint("feed_routes", __name__)

    @feed_routes.route("/feed/<email>")
    @deps["login_required"]
    def feed_page(email):
        current_user = deps["find_user_by_email"](email)

        if current_user is None:
            return "User not found"

        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", [])
        posts_html = ""
        feed_ranking = feed_ranking_service.rank_feed_posts(current_user, posts, {
            "calculate_ai_learning_boost": lambda user_email, post, content_language: deps["calculate_ai_learning_boost"](
                user_email,
                post,
                content_language,
            ),
            "can_view_feed_post": lambda viewer_email, post: deps["can_view_feed_post"](viewer_email, post),
            "clean_text": deps["clean_text"],
            "content_languages": deps["content_languages"],
            "detect_content_language": lambda text: deps["detect_content_language"](text),
            "find_user_by_email": lambda email: deps["find_user_by_email"](email),
            "get_current_language": lambda user: deps["get_current_language"](user),
            "get_user_language_signals": lambda user: deps["get_user_language_signals"](user),
            "normalize_content_language_code": lambda value: deps["normalize_content_language_code"](value),
            "normalize_email": deps["normalize_email"],
            "normalize_user_ai_settings": lambda email: deps["normalize_user_ai_settings"](email),
            "score_language_match": lambda user, content_language: deps["score_language_match"](user, content_language),
            "supported_languages": deps["supported_languages"],
        })
        ranked_posts = feed_ranking["ranked_posts"]
        user_language_codes = feed_ranking["user_language_codes"]
        user_language_names = feed_ranking["user_language_names"]
        ai_feed_enabled = feed_ranking["ai_feed_enabled"]
        ui = deps["translation_bundle"](deps["get_current_language"](current_user))

        def ui_text(key, fallback=""):
            return deps["safe_text"](ui.get(key, fallback or key))

        if feed_ranking["feed_changed"]:
            feed_data["posts"] = posts
            deps["save_feed"](feed_data)

        for item in ranked_posts:
            post = item.get("post", {})
            author = item.get("author")
            ai_reasons = item.get("ai_reasons", [])
            content_language = deps["normalize_content_language_code"](item.get("content_language", post.get("language", "unknown")))
            content_language_name = deps["content_languages"]().get(content_language, "Unknown")
            author_email = deps["normalize_email"](author.email)

            media_html = ""
            media_items = post.get("media_items", [])

            if not media_items and post.get("media_url"):
                media_items = [{"url": post.get("media_url", ""), "type": post.get("media_type", ""), "name": "media"}]

            for media in media_items[:4]:
                media_url = media.get("url", "")
                media_type = media.get("type", "")

                if media_url and media_type == "image":
                    media_html += f'<img src="{media_url}" style="width:100%;max-height:420px;object-fit:cover;border-radius:20px;margin-top:14px;">'
                elif media_url and media_type == "video":
                    media_html += f'<video src="{media_url}" controls playsinline style="width:100%;max-height:420px;border-radius:20px;margin-top:14px;background:#020617;"></video>'
                elif media_url and media_type == "audio":
                    media_html += f'<audio src="{media_url}" controls style="width:100%;margin-top:14px;"></audio>'

            hashtags_html = ""
            for tag in post.get("hashtags", [])[:8]:
                clean_tag = deps["clean_text"](tag).replace("#", "")
                hashtags_html += f'<a href="/hashtag/{deps["safe_text"](current_user.email)}/{deps["safe_text"](clean_tag)}" style="color:#93c5fd;text-decoration:none;background:rgba(37,99,235,0.14);padding:6px 9px;border-radius:999px;font-size:13px;font-weight:bold;">#{deps["safe_text"](clean_tag)}</a>'

            ai_reasons_html = ""
            for reason in ai_reasons:
                ai_reasons_html += f'<p style="margin:6px 0 0 0;color:#bfdbfe;">• {deps["safe_text"](reason)}</p>'

            message_link = ""
            if author_email != deps["normalize_email"](current_user.email):
                can_write, _, _ = deps["get_message_permission_status"](current_user, author)
                if can_write:
                    message_link = f'<a href="/chat/{deps["safe_text"](current_user.email)}/{deps["safe_text"](author.email)}" style="background:#16a34a;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">{ui_text("write_message", "Write")}</a>'
                else:
                    message_link = f'<span style="background:#475569;color:#cbd5e1;padding:10px 12px;border-radius:14px;font-weight:bold;">{ui_text("unavailable", "Unavailable")}</span>'

            translate_link = ""
            if content_language not in user_language_codes and content_language != "unknown":
                translate_link = f'<a href="/translate_post/{deps["safe_text"](current_user.email)}/{post.get("id")}" style="background:#7c3aed;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">🌍 {ui_text("ai_translation", "AI translation")}</a>'

            posts_html += f"""
            <div style="background:#1e293b;border-radius:28px;padding:22px;margin-bottom:18px;border:1px solid rgba(148,163,184,0.10);">
                <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:14px;">
                    <a href="/profile/{deps["safe_text"](author.email)}?viewer={deps["safe_text"](current_user.email)}" style="display:flex;align-items:center;gap:13px;color:white;text-decoration:none;">
                        <img src="{deps["get_avatar_url"](author.email)}" style="width:56px;height:56px;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #334155;">
                        <div>
                            <strong>{deps["safe_text"](author.name)}</strong>
                            <p style="margin:5px 0 0 0;color:#94a3b8;font-size:13px;">{deps["safe_text"](author.profession)} · {deps["safe_text"](post.get("location", ""))}</p>
                        </div>
                    </a>
                    <div style="background:linear-gradient(135deg,#2563eb,#7c3aed);border-radius:999px;padding:9px 12px;font-weight:bold;white-space:nowrap;">AI {int(max(0, min(item.get("score", 0), 100)))}%</div>
                </div>

                <div style="color:#60a5fa;font-weight:bold;margin-bottom:8px;">{deps["safe_text"](post.get("type", ui.get("post", "Post")))} · {deps["safe_text"](content_language_name)}</div>
                <p style="color:#e5e7eb;line-height:1.55;font-size:16px;white-space:pre-wrap;">{deps["safe_text"](post.get("text", ""))}</p>

                {media_html}

                <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;">
                    {hashtags_html}
                </div>

                <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.18);border-radius:20px;padding:14px;margin-top:16px;color:#dbeafe;">
                    <strong>🧠 {ui_text("why_ai_showed", "Why AI showed this:")}</strong>
                    {ai_reasons_html}
                </div>

                <div style="display:flex;flex-wrap:wrap;gap:9px;margin-top:16px;">
                    <a href="/like_post/{deps["safe_text"](current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">♡ {len(post.get("likes", []))}</a>
                    <a href="/post_comments/{deps["safe_text"](current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">💬 {len(post.get("comments", []))}</a>
                    <a href="/save_post/{deps["safe_text"](current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">🔖 {len(post.get("saves", []))}</a>
                    <a href="/post/{deps["safe_text"](current_user.email)}/{post.get("id")}" style="background:#334155;color:white;text-decoration:none;padding:10px 12px;border-radius:14px;font-weight:bold;">{ui_text("open", "Open")}</a>
                    {translate_link}
                    {message_link}
                </div>
            </div>
            """

        if posts_html == "":
            posts_html = f"""
            <div style="background:#1e293b;padding:28px;border-radius:26px;color:#cbd5e1;text-align:center;">
                <h2>{ui_text("feed_empty_title", "No posts yet")}</h2>
                <p>{ui_text("feed_empty_intro", "Create the first post, idea, video, or project. AI Discover will start building a smart feed around user interests.")}</p>
            </div>
            """

        user_languages_text = ", ".join(user_language_names) if user_language_names else ui.get("auto_language", "Auto")
        feed_mode_text = ui.get("ai_personalization_on", "AI personalization on") if ai_feed_enabled else ui.get("standard_feed", "Standard feed")

        return f"""
        <!DOCTYPE html>
        <html lang="{ui_text("language_code", "ru")}" dir="{ui_text("text_direction", "ltr")}">
        <head>
            <meta charset="UTF-8">
            <title>AI Discover - AI Match Life</title>
        </head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
            <div style="max-width:1080px;margin:auto;">
                <a href="/dashboard/{deps["safe_text"](current_user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← {ui_text("back", "Back")}</a>

                <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:30px;border-radius:30px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.14);">
                    <h1 style="margin:0 0 10px 0;font-size:34px;">🧠 AI Discover</h1>
                    <p style="margin:0;color:#cbd5e1;line-height:1.55;">{ui_text("ai_discover_intro", "A smart feed of videos, ideas, projects, places, and people. AI first raises content in a language you understand, then learns from your interests and activity.")}</p>
                    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;">
                        <span style="background:rgba(37,99,235,0.22);border:1px solid rgba(96,165,250,0.26);color:#bfdbfe;border-radius:999px;padding:8px 12px;font-weight:bold;font-size:13px;">{deps["safe_text"](feed_mode_text)}</span>
                        <span style="background:rgba(15,23,42,0.58);border:1px solid rgba(148,163,184,0.20);color:#cbd5e1;border-radius:999px;padding:8px 12px;font-weight:bold;font-size:13px;">{ui_text("your_languages", "Your languages")}: {deps["safe_text"](user_languages_text)}</span>
                    </div>
                </div>

                <div style="background:#1e293b;padding:22px;border-radius:26px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.10);">
                    <h2 style="margin:0 0 14px 0;">{ui_text("create_post", "Create post")}</h2>
                    <form method="POST" action="/create_post/{deps["safe_text"](current_user.email)}" enctype="multipart/form-data">
                        <input type="hidden" name="return_to" value="feed">
                        {deps["csrf_input"]()}
                        <select name="type" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                            <option value="idea">{ui_text("post_type_idea", "Thought / idea")}</option>
                            <option value="news">{ui_text("post_type_news", "News")}</option>
                            <option value="project">{ui_text("post_type_project", "Project")}</option>
                            <option value="partner">{ui_text("post_type_partner_search", "Partner search")}</option>
                            <option value="achievement">{ui_text("post_type_achievement", "Achievement")}</option>
                            <option value="Proof">{ui_text("post_type_proof", "Proof")}</option>
                        </select>
                        <select name="language" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                            <option value="">{ui_text("auto_detect_language", "Auto-detect language")}</option>
                            <option value="ru">Русский</option>
                            <option value="en">English</option>
                            <option value="de">Deutsch</option>
                            <option value="tr">Türkçe</option>
                            <option value="tk">Türkmençe</option>
                            <option value="uz">Oʻzbekcha</option>
                            <option value="ar">العربية</option>
                            <option value="es">Español</option>
                            <option value="fr">Français</option>
                            <option value="it">Italiano</option>
                            <option value="pt">Português</option>
                            <option value="pl">Polski</option>
                            <option value="uk">Українська</option>
                            <option value="zh">中文</option>
                        </select>
                        <input name="location" placeholder="{ui_text("city_country_placeholder", "City / country")}" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                        <input name="hashtags" placeholder="#business #restaurant #germany" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                        <textarea name="text" placeholder="{ui_text("post_text_placeholder", "What do you want to show the world? Idea, video, place, business, project...")}" required style="width:100%;min-height:110px;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;"></textarea>
                        <input type="file" name="media" multiple accept="image/*,video/*,audio/*" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:16px;padding:13px 14px;margin-bottom:12px;">
                        <button type="submit" style="background:#2563eb;color:white;border:none;border-radius:16px;padding:14px 18px;font-weight:bold;cursor:pointer;width:100%;">{ui_text("publish_to_ai_discover", "Publish to AI Discover")}</button>
                    </form>
                </div>

                {posts_html}
            </div>
        </body>
        </html>
        """

    @feed_routes.route("/create_post/<email>", methods=["POST"])
    @deps["login_required"]
    def create_post(email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        result = feed_post_creation_service.build_web_post(user, request.form, request.files.getlist("media"), deps["load_feed"](), {
            "allowed_mime_type": deps["allowed_mime_type"],
            "clean_text": deps["clean_text"],
            "detect_content_language": deps["detect_content_language"],
            "log_security_event": deps["log_security_event"],
            "normalize_content_language_code": deps["normalize_content_language_code"],
            "upload_folder": deps["upload_folder"]() if callable(deps["upload_folder"]) else deps["upload_folder"],
        })

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
