from flask import Blueprint, jsonify, request


def create_profile_api(deps):
    profile_api = Blueprint("profile_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    def current_user_or_error():
        user = deps["get_api_current_user"]()
        if user is None:
            return None, api_error("Authentication required", 401)
        return user, None

    @profile_api.route("/api/me")
    def api_me():
        user, error = current_user_or_error()
        if error:
            return error

        return jsonify({
            "ok": True,
            "user": deps["api_user_payload"](user),
            "privacy": deps["normalize_user_ai_settings"](user.email),
        })

    @profile_api.route("/api/me/onboarding", methods=["POST"])
    def api_me_onboarding():
        user, error = current_user_or_error()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        action = deps["clean_text"](data.get("action", "save"))

        if action == "skip":
            deps["profile_service"].skip_onboarding(user)
            deps["save_users_to_json"](deps["get_users"]())
            return jsonify({
                "ok": True,
                "user": deps["api_user_payload"](user),
                "next": "/api/matches",
            })

        deps["save_onboarding_answers"](user, data)

        return jsonify({
            "ok": True,
            "user": deps["api_user_payload"](user),
            "next": "/api/matches",
        })

    @profile_api.route("/api/me/profile", methods=["PATCH", "POST"])
    def api_update_profile():
        user, error = current_user_or_error()
        if error:
            return error

        data = request.get_json(silent=True) or {}
        deps["profile_service"].update_profile(user, data, list_limit=12)
        deps["calculate_trust_score"](user)
        deps["save_users_to_json"](deps["get_users"]())

        return jsonify({
            "ok": True,
            "user": deps["api_user_payload"](user),
        })

    @profile_api.route("/api/privacy", methods=["GET", "PATCH", "POST"])
    def api_privacy_settings():
        user, error = current_user_or_error()
        if error:
            return error

        if request.method == "GET":
            return jsonify({
                "ok": True,
                "settings": deps["normalize_user_ai_settings"](user.email),
            })

        data = request.get_json(silent=True) or {}
        current_settings = deps["normalize_user_ai_settings"](user.email)
        next_settings, validation_error = deps["privacy_service"].build_update(current_settings, data)
        if validation_error:
            return api_error(validation_error, 400)

        deps["save_user_ai_settings"](user.email, next_settings)

        return jsonify({
            "ok": True,
            "settings": deps["normalize_user_ai_settings"](user.email),
        })

    return profile_api
