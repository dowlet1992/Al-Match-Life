from flask import Blueprint, redirect, render_template, request

from backend.services import story_creation_service, story_view_service


def create_story_routes(deps):
    story_routes = Blueprint("story_routes", __name__)

    def story_copy(user):
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copies = {
            "ru": {"title": "Истории", "previous": "Предыдущая история", "next": "Следующая история", "close": "Закрыть истории", "reply": "Ответить…", "create_failed": "История не добавлена", "create_failed_help": "Файл не подходит. Добавьте фото или видео.", "blocked": "История недоступна", "blocked_help": "Историю нельзя просмотреть, потому что один из пользователей заблокировал другого.", "restricted_help": "Этот пользователь ограничил аудиторию своих историй.", "empty": "Историй пока нет", "empty_help": "У этого пользователя нет активных историй за последние 24 часа.", "unsafe": "Нет безопасного медиафайла для показа."},
            "de": {"title": "Stories", "previous": "Vorherige Story", "next": "Nächste Story", "close": "Stories schließen", "reply": "Antworten…", "create_failed": "Story wurde nicht hinzugefügt", "create_failed_help": "Die Datei ist ungeeignet. Fügen Sie ein Foto oder Video hinzu.", "blocked": "Story nicht verfügbar", "blocked_help": "Die Story kann nicht angesehen werden, weil eine Person die andere blockiert hat.", "restricted_help": "Diese Person hat die Zielgruppe ihrer Stories eingeschränkt.", "empty": "Noch keine Stories", "empty_help": "Diese Person hat keine aktiven Stories aus den letzten 24 Stunden.", "unsafe": "Es sind keine sicheren Story-Medien verfügbar."},
            "tr": {"title": "Hikâyeler", "previous": "Önceki hikâye", "next": "Sonraki hikâye", "close": "Hikâyeleri kapat", "reply": "Yanıtla…", "create_failed": "Hikâye eklenemedi", "create_failed_help": "Dosya uygun değil. Bir fotoğraf veya video ekleyin.", "blocked": "Hikâye kullanılamıyor", "blocked_help": "Kullanıcılardan biri diğerini engellediği için bu hikâye görüntülenemiyor.", "restricted_help": "Bu kullanıcı hikâyelerinin hedef kitlesini kısıtladı.", "empty": "Henüz hikâye yok", "empty_help": "Bu kullanıcının son 24 saat içinde etkin bir hikâyesi yok.", "unsafe": "Gösterilebilecek güvenli bir hikâye medyası yok."},
            "en": {"title": "Stories", "previous": "Previous story", "next": "Next story", "close": "Close stories", "reply": "Reply…", "create_failed": "Story was not added", "create_failed_help": "The file is not suitable. Add a photo or video.", "blocked": "Story unavailable", "blocked_help": "This story cannot be viewed because one person has blocked the other.", "restricted_help": "This person has restricted the audience for their stories.", "empty": "No stories yet", "empty_help": "This person has no active stories from the last 24 hours.", "unsafe": "No safe story media is available."},
        }
        return ui, copies.get(language, copies["en"])

    @story_routes.route("/create_story/<identifier>", methods=["POST"])
    @deps["login_required"]
    def create_story(identifier):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](identifier)

        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("story_owner_mismatch", user.email, "Create Story identifier did not match session")
            return "Forbidden", 403
        _, copy = story_copy(user)

        uploaded_files = request.files.getlist("story_media")
        if not uploaded_files:
            return redirect(f"/dashboard/{user.id}")

        upload_folder = deps["upload_folder"]() if callable(deps["upload_folder"]) else deps["upload_folder"]
        result = story_creation_service.create_stories(user, uploaded_files, deps["load_stories"](), {
            "allowed_mime_type": deps["allowed_mime_type"],
            "log_security_event": deps["log_security_event"],
            "upload_folder": upload_folder,
        })
        deps["save_stories"](result["stories_data"])

        if result.get("created_count", 0) == 0:
            return deps["simple_page"](
                copy["create_failed"],
                copy["create_failed_help"],
                user.email,
            )

        return redirect(f"/dashboard/{user.id}")

    @story_routes.route("/story/<viewer_identifier>/<owner_identifier>")
    @deps["login_required"]
    def view_story(viewer_identifier, owner_identifier):
        viewer = deps["find_user_by_identifier"](viewer_identifier)
        owner = deps["find_user_by_identifier"](owner_identifier)

        if viewer is None or owner is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](viewer.email):
            deps["log_security_event"]("story_viewer_mismatch", viewer.email, "Story viewer identifier did not match session")
            return "Forbidden", 403
        ui, copy = story_copy(viewer)

        view_result = story_view_service.prepare_story_view(viewer, owner, deps["load_stories"](), {
            "can_view_user_stories": deps["can_view_user_stories"],
            "is_blocked": deps["is_blocked"],
            "is_story_active": deps["is_story_active"],
            "log_security_event": deps["log_security_event"],
            "normalize_email": deps["normalize_email"],
        })

        if view_result.get("status") == "blocked":
            return deps["simple_page"](
                f"🚫 {copy['blocked']}",
                copy["blocked_help"],
                viewer.email,
            )

        if view_result.get("status") == "restricted":
            return deps["simple_page"](
                copy["blocked"],
                copy["restricted_help"],
                viewer.email,
            )

        if view_result.get("changed"):
            deps["save_stories"](view_result["stories_data"])

        owner_stories = view_result.get("owner_stories", [])

        if view_result.get("status") == "empty":
            return deps["simple_page"](
                copy["empty"],
                copy["empty_help"],
                viewer.email,
            )

        slides = []
        for story in owner_stories:
            media_url = str(story.get("media_url", ""))
            if not media_url.startswith(("/media-files/", "/static/")):
                deps["log_security_event"]("story_media_url_rejected", owner.email, "Non-local story media URL")
                continue
            slides.append({
                "media_url": media_url,
                "media_type": "video" if story.get("media_type") == "video" else "image",
            })
        if not slides:
            return deps["simple_page"](
                copy["title"],
                copy["unsafe"],
                viewer.email,
            )

        return render_template(
            "story_viewer.html",
            ui=ui,
            copy=copy,
            email=viewer.email,
            owner_avatar=deps["get_avatar_url"](owner.email),
            owner_name=owner.name,
            back_url=f"/dashboard/{viewer.id}",
            story_count_text=view_result.get("story_count_text", str(len(slides))),
            slides=slides,
        )

    return story_routes
