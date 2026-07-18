import os
import secrets
from datetime import datetime

from flask import Blueprint, redirect, request


def render_news_items(news_items, deps):
    if not news_items:
        return """
        <div style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:26px;padding:24px;color:#94a3b8;line-height:1.6;">
            Пока новостей нет.
        </div>
        """

    def render_news_media(media_items):
        if not isinstance(media_items, list) or not media_items:
            return ""

        media_html = ""
        for media in media_items:
            media_url = deps["safe_text"](media.get("url", ""))
            media_type = deps["clean_text"](media.get("type", ""))

            if not media_url or media_url == "Nicht angegeben":
                continue

            if media_type == "video":
                media_html += f"""
                <video controls playsinline style="width:100%;max-height:520px;border-radius:22px;margin-top:16px;background:#020617;object-fit:cover;">
                    <source src="{media_url}">
                </video>
                """
            else:
                media_html += f"""
                <img src="{media_url}" alt="News media" style="width:100%;max-height:520px;border-radius:22px;margin-top:16px;object-fit:cover;background:#020617;">
                """

        return media_html

    html = ""

    for item in reversed(news_items):
        title = deps["safe_text"](item.get("title", ""))
        body = deps["render_ai_text"](item.get("body", ""))
        author = deps["safe_text"](item.get("author_name", "AI Match Life"))
        created_at = deps["safe_text"](item.get("created_at", ""))
        source = deps["clean_text"](item.get("source", ""))
        location = deps["clean_text"](item.get("location", ""))
        media_html = render_news_media(item.get("media", []))
        source_html = ""
        location_html = ""

        if source:
            source_html = f"""
            <a href="{deps["safe_text"](source)}" target="_blank" rel="noopener noreferrer" style="display:inline-block;margin-top:14px;color:#93c5fd;text-decoration:none;font-weight:bold;">Источник</a>
            """

        if location:
            location_html = f"""
            <div style="display:inline-flex;margin-top:12px;background:#0f172a;color:#cbd5e1;border:1px solid rgba(148,163,184,0.14);border-radius:999px;padding:8px 12px;font-size:13px;font-weight:bold;">📍 {deps["safe_text"](location)}</div>
            """

        html += f"""
        <article style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:28px;padding:24px;margin-bottom:16px;box-shadow:0 18px 42px rgba(0,0,0,0.20);">
            <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
                <span style="color:#94a3b8;font-size:13px;">{author}</span>
                <span style="color:#64748b;font-size:13px;">{created_at}</span>
            </div>
            <h2 style="margin:0 0 12px 0;color:#f8fafc;line-height:1.25;font-size:24px;">{title}</h2>
            <div style="color:#cbd5e1;line-height:1.75;font-size:16px;">{body}</div>
            {media_html}
            {location_html}
            {source_html}
        </article>
        """

    return html


def create_news_routes(deps):
    news_routes = Blueprint("news_routes", __name__)

    @news_routes.route("/news/<email>", methods=["GET", "POST"])
    @deps["login_required"]
    def news_page(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            title = deps["clean_text"](request.form.get("title", ""))
            body = deps["clean_text"](request.form.get("body", ""))
            source = deps["clean_text"](request.form.get("source", ""))
            location = deps["clean_text"](request.form.get("location", ""))
            media_items = []

            try:
                files = request.files.getlist("media")
                for uploaded_file in files:
                    if (
                        uploaded_file
                        and uploaded_file.filename
                        and deps["allowed_file"](uploaded_file.filename)
                        and deps["allowed_mime_type"](uploaded_file)
                    ):
                        original_name = deps["secure_filename"](uploaded_file.filename)
                        extension = original_name.rsplit(".", 1)[1].lower() if "." in original_name else ""
                        stored_name = f"news_{secrets.token_urlsafe(10)}_{original_name}"
                        file_path = os.path.join(deps["upload_folder"](), stored_name)
                        uploaded_file.save(file_path)
                        media_type = "video" if extension in {"mp4", "webm", "mov"} else "image"
                        media_items.append({
                            "url": f"/static/uploads/{stored_name}",
                            "type": media_type,
                            "filename": stored_name,
                        })
            except Exception as error:
                deps["log_security_event"]("news_media_upload_failed", deps["normalize_email"](user.email), str(error))

            if not title or not body:
                message = "Заполните заголовок и текст."
            else:
                news_items = deps["load_news"]()
                news_items.append({
                    "id": secrets.token_urlsafe(10),
                    "author_email": deps["normalize_email"](user.email),
                    "author_name": deps["clean_text"](getattr(user, "name", "AI Match Life")),
                    "title": title,
                    "body": body,
                    "source": source,
                    "location": location,
                    "media": media_items,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                deps["save_news"](news_items)
                return redirect(f"/news/{deps["safe_text"](user.email)}")

        news_items = deps["load_news"]()
        news_html = render_news_items(news_items, deps)

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>News - AI Match Life</title>
        </head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
            <div style="max-width:1120px;margin:auto;">
                <a href="/dashboard/{deps["safe_text"](user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>

                <section style="background:linear-gradient(135deg,#1e293b,#111827);border:1px solid rgba(148,163,184,0.14);border-radius:30px;padding:30px;margin-bottom:22px;">
                    <h1 style="margin:0;font-size:34px;">🗞 News</h1>
                </section>

                <div style="display:grid;grid-template-columns:minmax(280px,360px) minmax(0,1fr);gap:18px;align-items:start;">
                    <aside style="background:#1e293b;border:1px solid rgba(148,163,184,0.10);border-radius:28px;padding:22px;position:sticky;top:18px;">
                        <h2 style="margin:0 0 14px 0;font-size:20px;">Добавить новость</h2>
                        <p style="color:#facc15;margin:0 0 12px 0;line-height:1.45;">{deps["safe_text"](message) if message else ''}</p>
                        <form method="POST" enctype="multipart/form-data">
                            {deps["csrf_input"]()}
                            <input name="title" placeholder="Заголовок" required style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;">
                            <textarea name="body" placeholder="Текст новости..." required style="width:100%;min-height:170px;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;line-height:1.5;"></textarea>
                            <label style="display:block;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;cursor:pointer;font-weight:bold;">
                                📷 Фото / 🎥 Видео
                                <input type="file" name="media" accept="image/*,video/*" capture="environment" multiple style="display:none;">
                            </label>
                            <input name="location" placeholder="📍 Местоположение" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:10px;">
                            <input name="source" placeholder="Источник / ссылка" style="width:100%;box-sizing:border-box;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:12px;">
                            <button type="submit" style="width:100%;background:#2563eb;color:white;border:none;border-radius:14px;padding:13px 16px;font-weight:bold;cursor:pointer;">Опубликовать</button>
                        </form>
                    </aside>

                    <main>
                        {news_html}
                    </main>
                </div>
            </div>
        </body>
        </html>
        """

    return news_routes
