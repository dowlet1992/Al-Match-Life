from io import BytesIO

from flask import Blueprint, redirect, render_template, request, send_file


REPORT_REASONS = ("spam", "fraud", "abuse", "fake_profile", "inappropriate_content", "other")


def create_profile_safety_routes(deps):
    profile_safety = Blueprint("profile_safety_routes", __name__)

    def profile_redirect(viewer, profile_user):
        return redirect(f"/profile/{deps['safe_text'](profile_user.id)}?viewer={deps['safe_text'](viewer.id)}")

    def page_copy(user):
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        language = ui.get("language_code", "en")
        copy = {
            "ru": {
                "qr_title": "QR-код профиля", "report_title": "Пожаловаться на профиль",
                "profile": "Профиль", "reason": "Причина", "comment": "Комментарий",
                "details_placeholder": "Опишите проблему…", "submit": "Отправить жалобу",
                "self_block_title": "Нельзя заблокировать себя", "self_block_message": "Вы не можете заблокировать собственный профиль.",
                "self_report_title": "Некорректная жалоба", "self_report_message": "Вы не можете пожаловаться на собственный профиль.",
                "report_sent_title": "Жалоба отправлена", "report_sent_message": "Мы получили вашу жалобу. Команда модерации проверит профиль и примет решение.",
                "reasons": {"spam": "Спам", "fraud": "Мошенничество", "abuse": "Оскорбления или угрозы", "fake_profile": "Фейковый профиль", "inappropriate_content": "Неподходящий контент", "other": "Другое"},
            },
            "de": {
                "qr_title": "Profil-QR-Code", "report_title": "Profil melden",
                "profile": "Profil", "reason": "Grund", "comment": "Kommentar",
                "details_placeholder": "Beschreiben Sie das Problem…", "submit": "Meldung senden",
                "self_block_title": "Sie können sich nicht selbst blockieren", "self_block_message": "Sie können Ihr eigenes Profil nicht blockieren.",
                "self_report_title": "Ungültige Meldung", "self_report_message": "Sie können Ihr eigenes Profil nicht melden.",
                "report_sent_title": "Meldung gesendet", "report_sent_message": "Wir haben Ihre Meldung erhalten. Das Moderationsteam wird das Profil prüfen.",
                "reasons": {"spam": "Spam", "fraud": "Betrug", "abuse": "Beleidigungen oder Drohungen", "fake_profile": "Gefälschtes Profil", "inappropriate_content": "Unangemessene Inhalte", "other": "Sonstiges"},
            },
            "en": {
                "qr_title": "Profile QR code", "report_title": "Report profile",
                "profile": "Profile", "reason": "Reason", "comment": "Comment",
                "details_placeholder": "Describe the problem…", "submit": "Submit report",
                "self_block_title": "You cannot block yourself", "self_block_message": "You cannot block your own profile.",
                "self_report_title": "Invalid report", "self_report_message": "You cannot report your own profile.",
                "report_sent_title": "Report submitted", "report_sent_message": "We received your report. The moderation team will review the profile.",
                "reasons": {"spam": "Spam", "fraud": "Fraud", "abuse": "Abuse or threats", "fake_profile": "Fake profile", "inappropriate_content": "Inappropriate content", "other": "Other"},
            },
            "tr": {
                "qr_title": "Profil QR kodu", "report_title": "Profili bildir",
                "profile": "Profil", "reason": "Neden", "comment": "Açıklama",
                "details_placeholder": "Sorunu açıklayın…", "submit": "Bildirimi gönder",
                "self_block_title": "Kendinizi engelleyemezsiniz", "self_block_message": "Kendi profilinizi engelleyemezsiniz.",
                "self_report_title": "Geçersiz bildirim", "self_report_message": "Kendi profilinizi bildiremezsiniz.",
                "report_sent_title": "Bildirim gönderildi", "report_sent_message": "Bildiriminizi aldık. Moderasyon ekibi profili inceleyip gerekli işlemi yapacaktır.",
                "reasons": {"spam": "Spam", "fraud": "Dolandırıcılık", "abuse": "Taciz veya tehdit", "fake_profile": "Sahte profil", "inappropriate_content": "Uygunsuz içerik", "other": "Diğer"},
            },
        }
        return ui, copy.get(language, copy["en"])

    def find_pair(viewer_identifier, profile_identifier):
        viewer = deps["find_user_by_identifier"](viewer_identifier)
        profile_user = deps["find_user_by_identifier"](profile_identifier)
        return viewer, profile_user

    @profile_safety.route("/block_user/<viewer_email>/<profile_email>", methods=["POST"], endpoint="block_user_profile_route")
    @deps["login_required"]
    def block_user_profile_route(viewer_email, profile_email):
        deps["validate_csrf_token"]()
        viewer, profile_user = find_pair(viewer_email, profile_email)

        if viewer is None or profile_user is None:
            return "User not found", 404

        if deps["normalize_email"](viewer.email) == deps["normalize_email"](profile_user.email):
            _, copy = page_copy(viewer)
            return deps["simple_page"](
                copy.get("self_block_title", "You cannot block yourself"),
                copy.get("self_block_message", "You cannot block your own profile."),
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

        profile_url = request.url_root.rstrip("/") + f"/profile/{profile_user.id}"
        qr_url = f"/profile_qr_image/{viewer.id}/{profile_user.id}"

        ui, copy = page_copy(viewer)
        return render_template(
            "profile_qr.html",
            ui=ui,
            copy=copy,
            email=viewer.email,
            profile_user=profile_user,
            profile_url=profile_url,
            qr_url=qr_url,
        )

    @profile_safety.route("/profile_qr_image/<viewer_email>/<profile_email>")
    @deps["login_required"]
    def profile_qr_image_route(viewer_email, profile_email):
        viewer, profile_user = find_pair(viewer_email, profile_email)
        if viewer is None or profile_user is None:
            return "User not found", 404

        import qrcode

        profile_url = request.url_root.rstrip("/") + f"/profile/{profile_user.id}"
        image = qrcode.make(profile_url)
        output = BytesIO()
        image.save(output, format="PNG")
        output.seek(0)
        response = send_file(output, mimetype="image/png", max_age=300)
        response.headers["Content-Disposition"] = "inline; filename=profile-qr.png"
        return response

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
        if deps["normalize_email"](viewer.email) == deps["normalize_email"](profile_user.email):
            _, copy = page_copy(viewer)
            return deps["simple_page"](
                copy.get("self_report_title", "Invalid report"),
                copy.get("self_report_message", "You cannot report your own profile."), viewer.email,
            ), 400

        if request.method == "POST":
            deps["validate_csrf_token"]()
            reason = deps["clean_text"](request.form.get("reason", "other"))
            if reason not in REPORT_REASONS:
                reason = "other"
            details = deps["clean_text"](request.form.get("details", ""))[:2000]
            deps["add_profile_report"](viewer.email, profile_user.email, reason, details)
            deps["log_security_event"]("user_reported", viewer.email, f"Reported {profile_user.email}; reason={reason}")
            _, copy = page_copy(viewer)
            return deps["simple_page"](
                copy.get("report_sent_title", "Report submitted"),
                copy.get("report_sent_message", "We received your report. The moderation team will review the profile."),
                viewer.email,
            )

        ui, copy = page_copy(viewer)
        return render_template(
            "report_profile.html",
            ui=ui,
            copy=copy,
            email=viewer.email,
            profile_user=profile_user,
            reasons=REPORT_REASONS,
            csrf_token_input=deps["csrf_input"](),
        )

    return profile_safety
