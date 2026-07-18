from flask import Blueprint, jsonify, request


def create_auth_api(deps):
    auth_api = Blueprint("auth_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    def auth_token_payload(user):
        create_access_token = deps.get("create_access_token")
        if not create_access_token:
            return {}
        return {
            "access_token": create_access_token(user.email),
            "token_type": "Bearer",
            "expires_in": deps.get("access_token_seconds", 0),
        }

    @auth_api.route("/api/auth/register", methods=["POST"])
    def api_auth_register():
        data = request.get_json(silent=True) or {}

        contact_type = deps["clean_text"](data.get("contact_type", "email")).lower()
        email_value = deps["normalize_email"](data.get("email", ""))
        phone_value = deps["normalize_phone"](data.get("phone", ""))
        raw_password = str(data.get("password", ""))

        if contact_type not in {"email", "phone"}:
            return api_error("Invalid registration method", 400)

        if contact_type == "email" and not email_value:
            return api_error("Email is required", 400)

        if contact_type == "phone" and not phone_value:
            return api_error("Phone number is required", 400)

        if email_value and deps["find_user_by_email"](email_value) is not None:
            return api_error("Account with this email already exists", 409)

        if phone_value and deps["find_user_by_contact"]("phone", phone_value) is not None:
            return api_error("Account with this phone number already exists", 409)

        if len(raw_password) < 8:
            return api_error("Password must contain at least 8 characters", 400)

        account_email_value = email_value
        if contact_type == "phone" and not account_email_value:
            account_email_value = deps["make_internal_phone_email"](phone_value)

        if not account_email_value:
            return api_error("Email or phone number is required", 400)

        try:
            age_value = int(data.get("age", 0))
        except Exception:
            age_value = 0

        if age_value < 16 or age_value > 120:
            return api_error("Age must be between 16 and 120", 400)

        new_user = deps["User"](
            deps["clean_text"](data.get("name", "")),
            age_value,
            account_email_value,
            raw_password,
            deps["clean_text"](data.get("country", "")),
            deps["clean_text"](data.get("bio", "")),
            deps["clean_text"](data.get("profession", "")),
            deps["clean_text"](data.get("looking_for", "")),
            deps["parse_short_list"](data.get("languages", ""), limit=12),
            deps["parse_short_list"](data.get("goals", ""), limit=12),
            deps["parse_short_list"](data.get("interests", ""), limit=12),
            deps["parse_short_list"](data.get("skills", ""), limit=12),
            account_verified=False,
            account_verified_at="",
            account_verified_via="",
        )

        new_user.phone = phone_value
        deps["calculate_trust_score"](new_user)
        deps["set_user_password"](new_user, raw_password)
        users = deps["get_users"]()
        users.append(new_user)
        deps["save_users_to_json"](users)

        contact_value = new_user.email if contact_type == "email" else phone_value
        code = deps["create_verification_code"]("account_verify", contact_type, contact_value)
        delivery_sent = False
        if code:
            delivery_sent = deps["send_verification_code"](contact_type, contact_value, code)
            deps["log_security_event"]("api_account_verification_code_sent", new_user.email, f"via={contact_type}")

        return jsonify({
            "ok": True,
            "verification_required": True,
            "delivery_sent": bool(delivery_sent),
            "contact_type": contact_type,
            "contact_value": contact_value,
            "user": deps["api_user_payload"](new_user),
        }), 201

    @auth_api.route("/api/auth/login", methods=["POST"])
    def api_auth_login():
        data = request.get_json(silent=True) or {}
        login_value = str(data.get("login", data.get("email", ""))).strip()
        password = str(data.get("password", ""))

        user, login_type, normalized_login = deps["find_user_by_login"](login_value)
        login_attempt_key = getattr(user, "email", normalized_login) if user is not None else normalized_login

        locked, minutes_left = deps["is_login_temporarily_locked"](login_attempt_key)
        if locked:
            return api_error(f"Too many login attempts. Try again in {minutes_left} minutes.", 429)

        if user is None or not deps["verify_user_password"](user, password):
            deps["register_failed_login_attempt"](login_attempt_key)
            return api_error("Invalid login or password", 401)

        if not deps["is_account_verified"](user):
            contact_type, contact_value = deps["get_user_2fa_contact"](user)
            code = deps["create_verification_code"]("account_verify", contact_type, contact_value)
            delivery_sent = False
            if code:
                delivery_sent = deps["send_verification_code"](contact_type, contact_value, code)

            return jsonify({
                "ok": True,
                "authenticated": False,
                "verification_required": True,
                "delivery_sent": bool(delivery_sent),
                "contact_type": contact_type,
                "contact_value": contact_value,
            }), 403

        deps["clear_login_attempts"](login_attempt_key)
        deps["api_login_session"](user)
        deps["log_security_event"]("api_login_success", user.email, "API login")

        response_payload = {
            "ok": True,
            "authenticated": True,
            "user": deps["api_user_payload"](user),
            "next": deps["onboarding_redirect_for"](user),
        }
        response_payload.update(auth_token_payload(user))
        return jsonify(response_payload)

    @auth_api.route("/api/auth/verify", methods=["POST"])
    def api_auth_verify():
        data = request.get_json(silent=True) or {}
        purpose = deps["clean_text"](data.get("purpose", "account_verify")).lower()
        contact_type = deps["clean_text"](data.get("contact_type", "email")).lower()
        contact_value = data.get("contact_value", "")
        code = data.get("code", "")

        if purpose not in {"account_verify", "login_2fa", "password_reset"}:
            return api_error("Invalid verification purpose", 400)

        if contact_type == "email":
            contact_value = deps["normalize_email"](contact_value)
        elif contact_type == "phone":
            contact_value = deps["normalize_phone"](contact_value)
        else:
            return api_error("Invalid contact type", 400)

        if not deps["verify_contact_code"](purpose, contact_type, contact_value, code):
            return api_error("Invalid or expired verification code", 400)

        user = deps["find_user_by_contact"](contact_type, contact_value)
        if user is None:
            return api_error("User not found", 404)

        if purpose in {"account_verify", "login_2fa"}:
            deps["mark_account_verified"](user, contact_type)
            deps["api_login_session"](user)

        response_payload = {
            "ok": True,
            "verified": True,
            "authenticated": purpose in {"account_verify", "login_2fa"},
            "user": deps["api_user_payload"](user),
            "next": deps["onboarding_redirect_for"](user),
        }
        if purpose in {"account_verify", "login_2fa"}:
            response_payload.update(auth_token_payload(user))
        return jsonify(response_payload)

    @auth_api.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        deps["clear_session"]()
        return jsonify({
            "ok": True,
            "authenticated": False,
        })

    return auth_api
