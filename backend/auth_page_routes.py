import urllib.parse
from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session

from backend.phone_country_codes import phone_country_options


def create_auth_page_routes(deps):
    auth_page_routes = Blueprint("auth_page_routes", __name__)

    @auth_page_routes.route("/")
    def home():
        ui = deps["translation_bundle"](deps["get_current_language"]())
        return render_template("index.html", csrf_token_input=deps["csrf_input"](), ui=ui)

    @auth_page_routes.route("/register", methods=["GET", "POST"])
    def register():
        ui = deps["translation_bundle"](deps["get_current_language"]())
        def registration_error(key, fallback, status=400):
            return ui.get(key, fallback), status

        if request.method == "POST":
            deps["validate_csrf_token"]()

            contact_type = deps["clean_text"](request.form.get("contact_type", "email")).lower()
            email_value = deps["normalize_email"](request.form.get("email", ""))
            phone_value = deps["normalize_phone"](request.form.get("phone", ""))
            raw_password = request.form.get("password", "")
            name = deps["clean_text"](request.form.get("name", ""))
            country = deps["clean_text"](request.form.get("country", ""))
            bio = deps["clean_text"](request.form.get("bio", ""))
            profession = deps["clean_text"](request.form.get("profession", ""))
            looking_for = deps["clean_text"](request.form.get("looking_for", ""))

            try:
                age = int(request.form.get("age", ""))
            except (TypeError, ValueError):
                return registration_error("registration_age_number", "Age must be a number.")

            if contact_type not in {"email", "phone"}:
                return registration_error("registration_method_invalid", "Choose email or phone registration.")

            if not 2 <= len(name) <= 120:
                return registration_error("registration_name_invalid", "Name must contain between 2 and 120 characters.")

            if not 16 <= age <= 120:
                return registration_error("registration_age_invalid", "Age must be between 16 and 120.")

            if not 2 <= len(country) <= 100:
                return registration_error("registration_country_invalid", "Country must contain between 2 and 100 characters.")

            if len(bio) > 500 or len(profession) > 120 or len(looking_for) > 120:
                return registration_error("registration_field_too_long", "One of the registration fields is too long.")

            if contact_type == "email" and not email_value:
                return registration_error("registration_email_required", "Email is required.")

            if contact_type == "phone" and not phone_value:
                return registration_error("registration_phone_required", "Phone number is required.")

            if len(email_value) > 254 or len(phone_value) > 16:
                return registration_error("registration_contact_too_long", "Contact information is too long.")

            if email_value and deps["find_user_by_email"](email_value) is not None:
                return registration_error("registration_email_exists", "An account with this email already exists.", 409)

            if phone_value and deps["find_user_by_contact"]("phone", phone_value) is not None:
                return registration_error("registration_phone_exists", "An account with this phone number already exists.", 409)

            if contact_type == "phone" and not email_value:
                internal_phone_email = deps["make_internal_phone_email"](phone_value)
                if internal_phone_email and deps["find_user_by_email"](internal_phone_email) is not None:
                    return registration_error("registration_phone_exists", "An account with this phone number already exists.", 409)

            if not 8 <= len(raw_password) <= 1024:
                return registration_error("registration_password_invalid", "Password must contain between 8 and 1024 characters.")

            account_email_value = email_value
            if contact_type == "phone" and not account_email_value:
                account_email_value = deps["make_internal_phone_email"](phone_value)

            if not account_email_value and not phone_value:
                return registration_error("registration_contact_required", "Email or phone number is required.")

            def clean_list(field_name):
                values = [
                    deps["clean_text"](item)
                    for item in request.form.get(field_name, "").split(",")
                    if deps["clean_text"](item)
                ]
                return [item[:80] for item in values[:20]]

            new_user = deps["User"](
                name,
                age,
                account_email_value,
                raw_password,
                country,
                bio,
                profession,
                looking_for,
                clean_list("languages"),
                clean_list("goals"),
                clean_list("interests"),
                clean_list("skills"),
            )

            new_user.phone = phone_value
            new_user.language = deps["get_current_language"]()
            new_user.account_verified = False
            new_user.account_verified_at = ""
            new_user.account_verified_via = ""

            deps["calculate_trust_score"](new_user)
            deps["set_user_password"](new_user, raw_password)
            deps["get_users"]().append(new_user)
            deps["save_users_to_json"](deps["get_users"]())
            deps["save_language_preference"](new_user.email, new_user.language)

            contact_value = new_user.email if contact_type == "email" else phone_value
            code = deps["create_verification_code"]("account_verify", contact_type, contact_value)
            if code:
                deps["send_verification_code"](contact_type, contact_value, code)
                deps["log_security_event"]("account_verification_code_sent", new_user.email, f"via={contact_type}")

            safe_contact_value = urllib.parse.quote(contact_value, safe="")
            return redirect(f"/verify_account?contact_type={contact_type}&contact_value={safe_contact_value}")

        return render_template(
            "register.html",
            csrf_token_input=deps["csrf_input"](),
            ui=ui,
            phone_countries=phone_country_options(),
        )

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

        return render_template(
            "auth_verify.html",
            ui=ui,
            icon="✅",
            title=ui.get("account_verification_title", "Account verification"),
            intro=ui.get("account_verification_intro", "Enter the 6-digit verification code."),
            method=f'{ui.get("verification_method", "Method")}: {contact_type} · {contact_value}',
            message=message,
            contact_type=contact_type,
            contact_value=contact_value,
            code_placeholder=ui.get("verification_code_placeholder", "6-digit code"),
            confirm=ui.get("confirm", "Confirm"),
            cancel=ui.get("back", "Back"),
            cancel_url="/",
            csrf_token_input=deps["csrf_input"](),
        )

    @auth_page_routes.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return redirect("/")
        deps["validate_csrf_token"]()
        login_value = request.form.get("login", request.form.get("email", "")).strip()
        password = request.form.get("password", "")

        user, login_type, normalized_login = deps["find_user_by_login"](login_value)
        login_attempt_key = getattr(user, "email", normalized_login) if user is not None else normalized_login

        locked, minutes_left = deps["is_login_temporarily_locked"](login_attempt_key)
        ui = deps["translation_bundle"](deps["get_current_language"](user) if user is not None else deps["get_current_language"]())
        if locked:
            return ui.get("login_locked", "Too many incorrect sign-in attempts. Try again in {minutes} min.").format(minutes=minutes_left), 429

        if user is None or not deps["verify_user_password"](user, password):
            deps["register_failed_login_attempt"](login_attempt_key)
            return ui.get("login_invalid_credentials", "Email, phone number, or password is incorrect."), 401

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
