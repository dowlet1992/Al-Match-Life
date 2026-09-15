import os
import secrets
from datetime import datetime
from urllib.parse import urlsplit

from flask import Blueprint, redirect, render_template, request


def safe_http_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


def normalized_news_items(news_items, deps):
    if not isinstance(news_items, list):
        return []

    result = []
    for item in reversed(news_items):
        if not isinstance(item, dict):
            continue
        media_items = []
        for media in item.get("media", []) if isinstance(item.get("media"), list) else []:
            if not isinstance(media, dict):
                continue
            media_url = str(media.get("url", ""))
            if not media_url.startswith(("/media-files/", "/static/")):
                continue
            media_items.append({
                "url": media_url,
                "type": "video" if media.get("type") == "video" else "image",
            })
        result.append({
            "title": deps["clean_text"](item.get("title", "")),
            "body": deps["clean_text"](item.get("body", "")),
            "author": deps["clean_text"](item.get("author_name", "NOVIX")),
            "created_at": deps["clean_text"](item.get("created_at", "")),
            "source": safe_http_url(item.get("source", "")),
            "location": deps["clean_text"](item.get("location", "")),
            "media": media_items,
        })
    return result


def create_news_routes(deps):
    news_routes = Blueprint("news_routes", __name__)

    def page_copy(user):
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copy = {
            "ru": {
                "title": "Новости", "add": "Добавить новость", "required": "Заполните заголовок и текст.",
                "headline": "Заголовок", "body": "Текст новости…", "media": "Фото / Видео",
                "location": "Местоположение", "source": "Источник / ссылка", "publish": "Опубликовать",
                "source_link": "Источник", "empty": "Пока новостей нет.",
            },
            "de": {
                "title": "Neuigkeiten", "add": "Neuigkeit hinzufügen", "required": "Titel und Text sind erforderlich.",
                "headline": "Titel", "body": "Nachrichtentext…", "media": "Foto / Video",
                "location": "Ort", "source": "Quelle / Link", "publish": "Veröffentlichen",
                "source_link": "Quelle", "empty": "Noch keine Neuigkeiten.",
            },
            "en": {
                "title": "News", "add": "Add news", "required": "Title and text are required.",
                "headline": "Title", "body": "News text…", "media": "Photo / Video",
                "location": "Location", "source": "Source / link", "publish": "Publish",
                "source_link": "Source", "empty": "No news yet.",
            },
            "tr": {
                "title": "Haberler", "add": "Haber ekle", "required": "Başlık ve metin gereklidir.",
                "headline": "Başlık", "body": "Haber metni…", "media": "Fotoğraf / Video",
                "location": "Konum", "source": "Kaynak / bağlantı", "publish": "Yayımla",
                "source_link": "Kaynak", "empty": "Henüz haber yok.",
            },
        }
        return ui, copy.get(language, copy["en"])

    @news_routes.route("/news/<identifier>", methods=["GET", "POST"])
    @deps["login_required"]
    def news_page(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("news_owner_mismatch", deps["current_session_email"](), f"target={user.email}")
            return "Forbidden", 403
        email = user.email

        ui, copy = page_copy(user)
        message = ""
        form_data = {"title": "", "body": "", "source": "", "location": ""}

        if request.method == "POST":
            deps["validate_csrf_token"]()
            form_data = {
                "title": deps["clean_text"](request.form.get("title", ""))[:160],
                "body": deps["clean_text"](request.form.get("body", ""))[:5000],
                "source": safe_http_url(request.form.get("source", "")),
                "location": deps["clean_text"](request.form.get("location", ""))[:160],
            }
            if not form_data["title"] or not form_data["body"]:
                message = copy["required"]
            else:
                media_items = []
                try:
                    for uploaded_file in request.files.getlist("media")[:8]:
                        if not (
                            uploaded_file
                            and uploaded_file.filename
                            and deps["allowed_file"](uploaded_file.filename)
                            and deps["allowed_mime_type"](uploaded_file)
                        ):
                            continue
                        original_name = deps["secure_filename"](uploaded_file.filename)
                        extension = original_name.rsplit(".", 1)[1].lower() if "." in original_name else ""
                        owner_id = deps["secure_filename"](str(getattr(user, "id", "") or ""))
                        stored_name = f"news_{owner_id}_{secrets.token_urlsafe(10)}.{extension}"
                        uploaded_file.save(os.path.join(deps["upload_folder"](), stored_name))
                        media_items.append({
                            "url": f"/media-files/{stored_name}",
                            "type": "video" if extension in {"mp4", "webm", "mov"} else "image",
                            "filename": original_name,
                        })
                except Exception as error:
                    deps["log_security_event"]("news_media_upload_failed", deps["normalize_email"](user.email), str(error))

                news_items = deps["load_news"]()
                if not isinstance(news_items, list):
                    news_items = []
                news_items.append({
                    "id": secrets.token_urlsafe(10),
                    "author_email": deps["normalize_email"](user.email),
                    "author_name": deps["clean_text"](getattr(user, "name", "NOVIX")),
                    **form_data,
                    "media": media_items,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })
                deps["save_news"](news_items)
                return redirect(f"/news/{user.email}", code=303)

        return render_template(
            "news.html",
            ui=ui,
            copy=copy,
            email=user.email,
            message=message,
            form_data=form_data,
            news_items=normalized_news_items(deps["load_news"](), deps),
            csrf_token_input=deps["csrf_input"](),
        )

    return news_routes
