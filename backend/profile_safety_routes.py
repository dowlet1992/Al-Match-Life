import urllib.parse

from flask import Blueprint, redirect, request


def create_profile_safety_routes(deps):
    profile_safety = Blueprint("profile_safety_routes", __name__)

    def profile_redirect(viewer, profile_user):
        return redirect(f"/profile/{deps['safe_text'](profile_user.email)}?viewer={deps['safe_text'](viewer.email)}")

    def find_pair(viewer_email, profile_email):
        viewer = deps["find_user_by_email"](viewer_email)
        profile_user = deps["find_user_by_email"](profile_email)
        return viewer, profile_user

    @profile_safety.route("/block_user/<viewer_email>/<profile_email>", methods=["POST"], endpoint="block_user_profile_route")
    @deps["login_required"]
    def block_user_profile_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        if deps["normalize_email"](viewer.email) == deps["normalize_email"](profile_user.email):
            return deps["simple_page"](
                "Нельзя заблокировать себя",
                "Вы не можете заблокировать собственный профиль.",
                viewer.email,
            )

        deps["block_user_account"](deps["normalize_email"](viewer.email), deps["normalize_email"](profile_user.email))
        deps["log_security_event"]("user_blocked", viewer.email, f"Blocked {profile_user.email}")
        return profile_redirect(viewer, profile_user)

    @profile_safety.route("/unblock_user/<viewer_email>/<profile_email>", methods=["POST"], endpoint="unblock_user_profile_route")
    @deps["login_required"]
    def unblock_user_profile_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        deps["unblock_user_account"](deps["normalize_email"](viewer.email), deps["normalize_email"](profile_user.email))
        deps["log_security_event"]("user_unblocked", viewer.email, f"Unblocked {profile_user.email}")
        return profile_redirect(viewer, profile_user)

    @profile_safety.route("/profile_qr/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def profile_qr_route(viewer_email, profile_email):
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        profile_url = request.url_root.rstrip("/") + f"/profile/{deps['safe_text'](profile_user.email)}?viewer={deps['safe_text'](viewer.email)}"
        qr_url = "https://api.qrserver.com/v1/create-qr-code/?size=260x260&data=" + urllib.parse.quote(profile_url)

        return render_profile_qr_page(viewer, profile_user, profile_url, qr_url, deps)

    @profile_safety.route("/restrict_user/<viewer_email>/<profile_email>", methods=["POST"])
    @deps["login_required"]
    def restrict_user_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        deps["restrict_user_account"](viewer.email, profile_user.email)
        deps["log_security_event"]("user_restricted", viewer.email, f"Restricted {profile_user.email}")
        return profile_redirect(viewer, profile_user)

    @profile_safety.route("/unrestrict_user/<viewer_email>/<profile_email>", methods=["POST"])
    @deps["login_required"]
    def unrestrict_user_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        deps["unrestrict_user_account"](viewer.email, profile_user.email)
        deps["log_security_event"]("user_unrestricted", viewer.email, f"Unrestricted {profile_user.email}")
        return profile_redirect(viewer, profile_user)

    @profile_safety.route("/hide_stories/<viewer_email>/<profile_email>", methods=["POST"])
    @deps["login_required"]
    def hide_stories_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        deps["hide_stories_from_user"](viewer.email, profile_user.email)
        deps["log_security_event"]("stories_hidden", viewer.email, f"Hidden stories from {profile_user.email}")
        return profile_redirect(viewer, profile_user)

    @profile_safety.route("/show_stories/<viewer_email>/<profile_email>", methods=["POST"])
    @deps["login_required"]
    def show_stories_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        deps["show_stories_from_user"](viewer.email, profile_user.email)
        deps["log_security_event"]("stories_shown", viewer.email, f"Shown stories from {profile_user.email}")
        return profile_redirect(viewer, profile_user)

    @profile_safety.route("/report_user/<viewer_email>/<profile_email>", methods=["GET", "POST"])
    @deps["login_required"]
    def report_user_route(viewer_email, profile_email):
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        if request.method == "POST":
            deps["validate_csrf_token"]()
            reason = deps["clean_text"](request.form.get("reason", "Другое"))
            details = deps["clean_text"](request.form.get("details", ""))
            deps["add_profile_report"](viewer.email, profile_user.email, reason, details)
            deps["log_security_event"]("user_reported", viewer.email, f"Reported {profile_user.email}; reason={reason}")
            return deps["simple_page"](
                "Жалоба отправлена",
                "Мы получили вашу жалобу. Команда модерации проверит профиль и примет решение.",
                viewer.email,
            )

        return render_report_user_page(viewer, profile_user, deps)

    return profile_safety


def render_profile_qr_page(viewer, profile_user, profile_url, qr_url, deps):
    safe_text = deps["safe_text"]
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>QR-код профиля</title>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px;">
        <main style="max-width:460px;width:100%;background:#1e293b;border:1px solid rgba(148,163,184,0.14);border-radius:30px;padding:28px;text-align:center;box-shadow:0 24px 70px rgba(0,0,0,0.32);">
            <a href="/profile/{safe_text(profile_user.email)}?viewer={safe_text(viewer.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;border-radius:14px;padding:11px 14px;font-weight:bold;margin-bottom:18px;">← Назад</a>
            <h1 style="margin:0 0 8px 0;">QR-код профиля</h1>
            <p style="color:#cbd5e1;margin:0 0 20px 0;line-height:1.5;">{safe_text(profile_user.name)}</p>
            <div style="background:white;border-radius:24px;padding:18px;display:inline-block;">
                <img src="{safe_text(qr_url)}" alt="QR Code" style="width:260px;height:260px;display:block;">
            </div>
            <p style="color:#94a3b8;word-break:break-all;font-size:13px;line-height:1.5;margin:18px 0 0 0;">{safe_text(profile_url)}</p>
        </main>
    </body>
    </html>
    """


def render_report_user_page(viewer, profile_user, deps):
    safe_text = deps["safe_text"]
    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Пожаловаться</title>
    </head>
    <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:24px;">
        <main style="max-width:620px;margin:auto;background:#1e293b;border:1px solid rgba(148,163,184,0.14);border-radius:30px;padding:28px;box-shadow:0 24px 70px rgba(0,0,0,0.32);">
            <a href="/profile/{safe_text(profile_user.email)}?viewer={safe_text(viewer.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;border-radius:14px;padding:11px 14px;font-weight:bold;margin-bottom:18px;">← Назад</a>
            <h1 style="margin:0 0 10px 0;">Пожаловаться на профиль</h1>
            <p style="color:#cbd5e1;line-height:1.5;margin:0 0 18px 0;">Профиль: {safe_text(profile_user.name)}</p>
            <form method="POST">
                {deps["csrf_input"]()}
                <label style="display:block;color:#cbd5e1;font-weight:bold;margin-bottom:8px;">Причина</label>
                <select name="reason" style="width:100%;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;margin-bottom:14px;">
                    <option>Спам</option>
                    <option>Мошенничество</option>
                    <option>Оскорбления или угрозы</option>
                    <option>Фейковый профиль</option>
                    <option>Неподходящий контент</option>
                    <option>Другое</option>
                </select>
                <label style="display:block;color:#cbd5e1;font-weight:bold;margin-bottom:8px;">Комментарий</label>
                <textarea name="details" placeholder="Опишите проблему..." style="width:100%;min-height:150px;background:#0f172a;color:white;border:1px solid #334155;border-radius:14px;padding:12px;box-sizing:border-box;line-height:1.5;margin-bottom:14px;"></textarea>
                <button type="submit" style="width:100%;background:#dc2626;color:white;border:none;border-radius:14px;padding:13px 16px;font-weight:bold;cursor:pointer;">Отправить жалобу</button>
            </form>
        </main>
    </body>
    </html>
    """
