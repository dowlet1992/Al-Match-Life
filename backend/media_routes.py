import os

from flask import Blueprint, redirect, render_template, request, send_from_directory
from werkzeug.exceptions import NotFound


def create_media_routes(deps):
    media_routes = Blueprint("media_routes", __name__)

    @media_routes.route("/media-files/<path:filename>")
    @deps["login_required"]
    def stream_media_file(filename):
        if not deps["can_access_media_file"](filename):
            raise NotFound()
        response = None
        for folder in deps["upload_folders"]():
            try:
                response = send_from_directory(
                    folder,
                    filename,
                    conditional=True,
                    max_age=86400,
                )
                break
            except NotFound:
                continue
        if response is None:
            raise NotFound()
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response

    @media_routes.route("/media/<identifier>", methods=["GET", "POST"])
    @deps["login_required"]
    def media_page(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("media_owner_mismatch", deps["current_session_email"](), f"target={user.email}")
            return "Forbidden", 403
        email = user.email

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copy = {
            "ru": ("Аватар и медиа", "Выбрать изображение", "Загрузить", "Назад", "Аватар успешно загружен.", "Файл не прошёл проверку безопасности. Разрешены PNG, JPG, JPEG, GIF или WEBP."),
            "en": ("Avatar and media", "Choose image", "Upload", "Back", "Avatar uploaded successfully.", "The file failed security validation. PNG, JPG, JPEG, GIF, or WEBP files are allowed."),
            "de": ("Avatar und Medien", "Bild auswählen", "Hochladen", "Zurück", "Profilbild erfolgreich hochgeladen.", "Die Datei hat die Sicherheitsprüfung nicht bestanden. PNG, JPG, JPEG, GIF oder WEBP sind erlaubt."),
            "tr": ("Profil resmi ve medya", "Görsel seç", "Yükle", "Geri", "Profil resmi başarıyla yüklendi.", "Dosya güvenlik doğrulamasını geçemedi. PNG, JPG, JPEG, GIF veya WEBP dosyalarına izin verilir."),
        }.get(language, ("Avatar and media", "Choose image", "Upload", "Back", "Avatar uploaded successfully.", "The file failed security validation."))
        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            file = request.files.get("avatar")

            if file and deps["allowed_file"](file.filename) and deps["allowed_mime_type"](file):
                extension = file.filename.rsplit(".", 1)[1].lower()
                filename = deps["avatar_filename"](email, extension)
                for stem in deps["avatar_file_stems"](email):
                    for ext in deps["allowed_extensions"]():
                        old_path = os.path.join(deps["upload_folder"](), f"{stem}.{ext}")
                        if os.path.exists(old_path):
                            os.remove(old_path)

                file.save(os.path.join(deps["upload_folder"](), filename))
                message = copy[4]
            else:
                deps["log_security_event"]("upload_rejected", email, "Invalid media page avatar upload")
                message = copy[5]
        return render_template(
            "media.html",
            ui=ui,
            title=copy[0],
            choose_file=copy[1],
            upload=copy[2],
            back=copy[3],
            email=deps["safe_text"](email),
            user_name=deps["safe_text"](user.name),
            avatar_url=deps["get_avatar_url"](user.email),
            message=deps["safe_text"](message),
            csrf_token_input=deps["csrf_input"](),
        )

    @media_routes.route("/quick_avatar/<identifier>", methods=["POST"])
    @deps["login_required"]
    def quick_avatar(identifier):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](identifier)

        if user is None:
            return "User not found", 404
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("quick_avatar_owner_mismatch", deps["current_session_email"](), f"target={user.email}")
            return "Forbidden", 403
        email = user.email

        file = request.files.get("avatar")

        if not file or not file.filename:
            return redirect(f"/dashboard/{email}")

        if not deps["allowed_file"](file.filename):
            deps["log_security_event"]("upload_rejected", email, "Unsupported avatar file extension")
            return "Unsupported avatar file type"

        if not deps["allowed_mime_type"](file):
            deps["log_security_event"]("upload_rejected", email, "Invalid avatar file content")
            return "Invalid file content"

        extension = file.filename.rsplit(".", 1)[1].lower()
        filename = deps["avatar_filename"](email, extension)
        for stem in deps["avatar_file_stems"](email):
            for old_ext in deps["allowed_extensions"]():
                old_path = os.path.join(deps["upload_folder"](), f"{stem}.{old_ext}")
                if os.path.exists(old_path):
                    os.remove(old_path)

        file.save(os.path.join(deps["upload_folder"](), filename))

        return redirect(f"/dashboard/{email}")

    return media_routes
