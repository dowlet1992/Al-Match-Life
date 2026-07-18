import os

from flask import Blueprint, redirect, request


def create_media_routes(deps):
    media_routes = Blueprint("media_routes", __name__)

    @media_routes.route("/media/<email>", methods=["GET", "POST"])
    @deps["login_required"]
    def media_page(email):
        user = deps["find_user_by_email"](email)
        if user is None:
            return "User not found"

        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            file = request.files.get("avatar")

            if file and deps["allowed_file"](file.filename) and deps["allowed_mime_type"](file):
                extension = file.filename.rsplit(".", 1)[1].lower()
                filename = deps["avatar_filename"](email, extension)
                safe_email = deps["secure_filename"](email.replace("@", "_at_").replace(".", "_"))

                for ext in deps["allowed_extensions"]():
                    old_path = os.path.join(deps["upload_folder"](), f"{safe_email}.{ext}")
                    if os.path.exists(old_path):
                        os.remove(old_path)

                file.save(os.path.join(deps["upload_folder"](), filename))
                message = "Аватар успешно загружен."
            else:
                deps["log_security_event"]("upload_rejected", email, "Invalid media page avatar upload")
                message = "Ошибка: файл не прошёл проверку безопасности. Разрешены только настоящие PNG, JPG, JPEG, GIF или WEBP."

        avatar_url = deps["get_avatar_url"](user.email)

        return f"""
        <html>
        <head>
        <meta charset="UTF-8">
        <title>Аватар и медиа</title>
        <style>
        body{{background:#0f172a;color:white;font-family:Arial;padding:40px}}
        .card{{background:#1e293b;padding:30px;border-radius:20px;max-width:600px;margin:auto;text-align:center}}
        img{{width:220px;height:220px;border-radius:50%;object-fit:cover;border:4px solid #334155;margin-bottom:25px}}
        input{{margin:20px 0}}
        button{{width:100%;padding:12px;border:none;border-radius:10px;background:#2563eb;color:white;cursor:pointer;margin-top:10px}}
        .back{{background:#334155}}
        .msg{{color:#22c55e}}
        </style>
        </head>
        <body>
        <div class="card">
            <h1>📸 Аватар и медиа</h1>
            <p>{deps["safe_text"](user.name)}</p>

            <img src="{avatar_url}" alt="Avatar">

            <p class="msg">{deps["safe_text"](message)}</p>

            <form method="POST" enctype="multipart/form-data">
                {deps["csrf_input"]()}
                <input type="file" name="avatar" accept="image/*" required>
                <button type="submit">Загрузить аватар</button>
            </form>

            <button class="back" onclick="window.location.href='/dashboard/{deps["safe_text"](email)}'">Назад в Dashboard</button>
        </div>
        </body>
        </html>
        """

    @media_routes.route("/quick_avatar/<email>", methods=["POST"])
    @deps["login_required"]
    def quick_avatar(email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found"

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
        safe_email = deps["secure_filename"](email.replace("@", "_at_").replace(".", "_"))

        for old_ext in deps["allowed_extensions"]():
            old_path = os.path.join(deps["upload_folder"](), f"{safe_email}.{old_ext}")
            if os.path.exists(old_path):
                os.remove(old_path)

        file.save(os.path.join(deps["upload_folder"](), filename))

        return redirect(f"/dashboard/{email}")

    return media_routes
