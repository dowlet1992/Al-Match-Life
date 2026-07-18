import urllib.parse
from datetime import datetime

from flask import Blueprint, redirect, render_template_string, request, session


def create_auth_page_routes(deps):
    auth_page_routes = Blueprint("auth_page_routes", __name__)

    @auth_page_routes.route("/")
    def home():
        html = deps["open_html"]("index.html")
        ui = deps["translation_bundle"](deps["get_current_language"]())
        return render_template_string(html, csrf_token_input=deps["csrf_input"](), ui=ui)

    @auth_page_routes.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            deps["validate_csrf_token"]()

            contact_type = deps["clean_text"](request.form.get("contact_type", "email")).lower()
            email_value = deps["normalize_email"](request.form.get("email", ""))
            phone_value = deps["normalize_phone"](request.form.get("phone", ""))
            raw_password = request.form.get("password", "")

            if contact_type not in {"email", "phone"}:
                return "Invalid registration method", 400

            if contact_type == "email" and not email_value:
                return "Email is required", 400

            if contact_type == "phone" and not phone_value:
                return "Phone number is required", 400

            if email_value and deps["find_user_by_email"](email_value) is not None:
                return "Account with this email already exists", 409

            if phone_value and deps["find_user_by_contact"]("phone", phone_value) is not None:
                return "Account with this phone number already exists", 409

            if contact_type == "phone" and not email_value:
                internal_phone_email = deps["make_internal_phone_email"](phone_value)
                if internal_phone_email and deps["find_user_by_email"](internal_phone_email) is not None:
                    return "Account with this phone number already exists", 409

            if len(raw_password) < 8:
                return "Password must contain at least 8 characters", 400

            account_email_value = email_value
            if contact_type == "phone" and not account_email_value:
                account_email_value = deps["make_internal_phone_email"](phone_value)

            if not account_email_value and not phone_value:
                return "Email or phone number is required", 400

            new_user = deps["User"](
                deps["clean_text"](request.form["name"]),
                int(request.form["age"]),
                account_email_value,
                raw_password,
                deps["clean_text"](request.form["country"]),
                deps["clean_text"](request.form["bio"]),
                deps["clean_text"](request.form["profession"]),
                deps["clean_text"](request.form["looking_for"]),
                [deps["clean_text"](item) for item in request.form["languages"].split(",") if deps["clean_text"](item)],
                [deps["clean_text"](item) for item in request.form["goals"].split(",") if deps["clean_text"](item)],
                [deps["clean_text"](item) for item in request.form["interests"].split(",") if deps["clean_text"](item)],
                [deps["clean_text"](item) for item in request.form["skills"].split(",") if deps["clean_text"](item)],
            )

            new_user.phone = phone_value
            new_user.account_verified = False
            new_user.account_verified_at = ""
            new_user.account_verified_via = ""

            deps["calculate_trust_score"](new_user)
            deps["set_user_password"](new_user, raw_password)
            deps["get_users"]().append(new_user)
            deps["save_users_to_json"](deps["get_users"]())

            contact_value = new_user.email if contact_type == "email" else phone_value
            code = deps["create_verification_code"]("account_verify", contact_type, contact_value)
            if code:
                deps["send_verification_code"](contact_type, contact_value, code)
                deps["log_security_event"]("account_verification_code_sent", new_user.email, f"via={contact_type}")

            safe_contact_value = urllib.parse.quote(contact_value, safe="")
            return redirect(f"/verify_account?contact_type={contact_type}&contact_value={safe_contact_value}")

        html = deps["open_html"]("register.html")
        ui = deps["translation_bundle"](deps["get_current_language"]())
        return render_template_string(html, csrf_token_input=deps["csrf_input"](), ui=ui)

    @auth_page_routes.route("/verify_account", methods=["GET", "POST"])
    def verify_account():
        ui = deps["translation_bundle"](deps["get_current_language"]())
        contact_type = deps["clean_text"](
            request.args.get("contact_type", request.form.get("contact_type", "email"))
        ).lower()
        contact_value = request.args.get("contact_value", request.form.get("contact_value", ""))
        if contact_type == "phone" and contact_value and not str(contact_value).strip().startswith("+"):
            digits_only = str(contact_value).strip().replace(" ", "")
            if digits_only.startswith("491") or digits_only.startswith("49"):
                contact_value = "+" + digits_only
        message = ""

        if contact_type not in {"email", "phone"}:
            contact_type = "email"

        if contact_type == "email":
            contact_value = deps["normalize_email"](contact_value)
        else:
            contact_value = deps["normalize_phone"](contact_value)

        if request.method == "POST":
            deps["validate_csrf_token"]()
            code = request.form.get("code", "")
            user = deps["find_user_by_contact"](contact_type, contact_value)

            if user is not None and deps["verify_contact_code"]("account_verify", contact_type, contact_value, code):
                deps["mark_account_verified"](user, contact_type)
                csrf_token = session.get("csrf_token")
                session.clear()
                session.permanent = True
                if csrf_token:
                    session["csrf_token"] = csrf_token
                session["user_email"] = user.email
                session["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                deps["bind_session_to_user"](user)
                session.modified = True
                deps["log_security_event"]("account_verified", getattr(user, "email", ""), f"via={contact_type}")
                return redirect(deps["onboarding_redirect_for"](user), code=303)

            deps["log_security_event"]("account_verify_failed", contact_value, f"via={contact_type}")
            message = ui.get("verification_invalid_code", "Invalid or expired code.")

        return f"""
        <html lang="{deps["safe_text"](ui.get("language_code", "en"))}" dir="{deps["safe_text"](ui.get("text_direction", "ltr"))}">
        <head>
            <meta charset="UTF-8">
            <title>{deps["safe_text"](ui.get("account_verification_title", "Account verification"))}</title>
            {deps["page_style"]()}
        </head>
        <body>
            <div class="card">
                <h1>✅ {deps["safe_text"](ui.get("account_verification_title", "Account verification"))}</h1>
                <p>{deps["safe_text"](ui.get("account_verification_intro", "Enter the 6-digit verification code."))}</p>
                <p style="color:#94a3b8;">{deps["safe_text"](ui.get("verification_method", "Method"))}: {deps["safe_text"](contact_type)} · {deps["safe_text"](contact_value)}</p>
                <p style="color:#facc15;">{deps["safe_text"](message)}</p>

                <form method="POST">
                    {deps["csrf_input"]()}
                    <input type="hidden" name="contact_type" value="{deps["safe_text"](contact_type)}">
                    <input type="hidden" name="contact_value" value="{deps["safe_text"](contact_value)}">
                    <input name="code" placeholder="{deps["safe_text"](ui.get("verification_code_placeholder", "6-digit code"))}" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                    <button type="submit">{deps["safe_text"](ui.get("confirm", "Confirm"))}</button>
                </form>

                <button class="back" onclick="window.location.href='/'">{deps["safe_text"](ui.get("back", "Back"))}</button>
            </div>
        </body>
        </html>
        """

    @auth_page_routes.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return redirect("/")
        deps["validate_csrf_token"]()
        login_value = request.form.get("login", request.form.get("email", "")).strip()
        password = request.form["password"]

        user, login_type, normalized_login = deps["find_user_by_login"](login_value)
        login_attempt_key = getattr(user, "email", normalized_login) if user is not None else normalized_login

        locked, minutes_left = deps["is_login_temporarily_locked"](login_attempt_key)
        if locked:
            return f"Слишком много неправильных попыток входа. Попробуйте через {minutes_left} мин."

        if user is None or not deps["verify_user_password"](user, password):
            deps["register_failed_login_attempt"](login_attempt_key)
            return "Неверный email/телефон или пароль"

        if not deps["is_account_verified"](user):
            contact_type, contact_value = deps["get_user_2fa_contact"](user)
            code = deps["create_verification_code"]("account_verify", contact_type, contact_value)
            if code:
                deps["send_verification_code"](contact_type, contact_value, code)
            deps["log_security_event"]("login_unverified_account", user.email, f"Login blocked until account verification via {contact_type}")
            safe_contact_value = urllib.parse.quote(contact_value, safe="")
            return redirect(f"/verify_account?contact_type={contact_type}&contact_value={safe_contact_value}")

        if deps["is_account_deactivated"](user):
            deps["save_user_ai_settings"](user.email, {"account_deactivated": False})
            deps["log_security_event"]("account_reactivated", user.email, "User restored account by signing in")

        deps["clear_login_attempts"](login_attempt_key)

        csrf_token = session.get("csrf_token")
        session_language = session.get("language")

        if not deps["user_requires_login_2fa"](user):
            session.clear()
            session.permanent = True
            if csrf_token:
                session["csrf_token"] = csrf_token
            if session_language:
                session["language"] = session_language
            session["user_email"] = user.email
            session["login_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            deps["bind_session_to_user"](user)
            session.modified = True
            deps["log_security_event"]("login_success", user.email, "2FA not required")
            deps["record_trusted_device_seen"](user)
            deps["send_login_alert"](user)
            return redirect(deps["onboarding_redirect_for"](user), code=303)

        contact_type, contact_value = deps["get_user_2fa_contact"](user)
        code = deps["create_verification_code"]("login_2fa", contact_type, contact_value)
        if code:
            deps["send_verification_code"](contact_type, contact_value, code)

        session.clear()
        session.permanent = True
        if csrf_token:
            session["csrf_token"] = csrf_token
        if session_language:
            session["language"] = session_language
        session["pending_2fa_email"] = user.email
        session["pending_2fa_contact_type"] = contact_type
        session["pending_2fa_contact_value"] = contact_value
        session.modified = True

        deps["log_security_event"]("login_2fa_required", user.email, f"via={contact_type}")
        safe_pending_email = urllib.parse.quote(user.email, safe="")
        safe_contact_type = urllib.parse.quote(contact_type, safe="")
        safe_contact_value = urllib.parse.quote(contact_value, safe="")
        return redirect(
            f"/verify_login_2fa?email={safe_pending_email}&contact_type={safe_contact_type}&contact_value={safe_contact_value}",
            code=303,
        )

    return auth_page_routes
