from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, make_response, redirect, render_template, request, send_from_directory, session


def create_account_page_routes(deps):
    routes = Blueprint("account_page_routes", __name__)

    @routes.route("/set_language/<identifier>/<language>", methods=["POST"])
    @deps["login_required"]
    def set_language_route(identifier, language):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            abort(403)
        language = deps["normalize_language_code"](language)
        deps["save_language_preference"](user.email, language)
        session["language"] = language
        session.modified = True
        user.language = language
        redirect_target = deps["safe_redirect_target"](request.referrer, f"/settings/{user.id}")
        if request.headers.get("X-Requested-With") == "fetch":
            return jsonify({"ok": True, "language": language, "redirect": redirect_target})
        return redirect(redirect_target, code=303)

    @routes.route("/onboarding/<identifier>", methods=["GET", "POST"])
    @deps["login_required"]
    def onboarding_page(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            deps["log_security_event"]("onboarding_owner_mismatch", deps["current_session_email"](), f"target={user.email}")
            abort(403)
        if request.method == "POST":
            deps["validate_csrf_token"]()
            action = deps["clean_text"](request.form.get("action", "save"))
            if action == "skip":
                deps["skip_onboarding"](user)
                deps["save_users"]()
                deps["log_security_event"]("onboarding_skipped", user.email, "User skipped optional onboarding")
                return redirect(f"/dashboard/{user.id}", code=303)
            deps["save_onboarding_answers"](user, request.form)
            deps["log_security_event"]("onboarding_completed", user.email, "User completed optional onboarding")
            return redirect(f"/matches/{user.id}", code=303)
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        ai_hint = deps["analyze_user_profile"](user)
        return render_template(
            "onboarding.html", ui=ui, email=user.email,
            ai_summary=ai_hint.get("summary", ui.get("onboarding_hint_default", "")),
            profile={
                "looking_for": getattr(user, "looking_for", ""), "profession": getattr(user, "profession", ""),
                "goals": ", ".join(getattr(user, "goals", []) or []), "interests": ", ".join(getattr(user, "interests", []) or []),
                "skills": ", ".join(getattr(user, "skills", []) or []), "languages": ", ".join(getattr(user, "languages", []) or []),
            }, csrf_token_input=deps["csrf_input"](),
        )

    @routes.route("/settings/<identifier>")
    @deps["login_required"]
    def settings_page(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            deps["log_security_event"]("settings_access_denied", deps["current_session_email"](), f"target={user.email}")
            abort(403)
        current_language = deps["get_current_language"](user)
        response = make_response(render_template(
            "settings.html", email=deps["safe_text"](user.email), user_id=user.id,
            settings=deps["normalize_user_ai_settings"](user.email), user=user,
            current_language=current_language, supported_languages=deps["ui_languages"],
            translation_languages=deps["translation_languages"],
            ui=deps["translation_bundle"](current_language), csrf_token_input=deps["csrf_input"](),
        ))
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Cookie, Accept-Language"
        return response

    @routes.route("/settings/<identifier>/privacy_ai", methods=["POST"])
    @deps["login_required"]
    def update_privacy_ai_settings(identifier):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            abort(403)
        current_settings = deps["normalize_user_ai_settings"](user.email)
        new_settings, language = deps["parse_privacy_ai_form"](request.form)
        if language:
            user.language = language
            session["language"] = language
            deps["save_users"]()
        merged_settings, validation_error = deps["build_privacy_update"](current_settings, new_settings)
        if validation_error:
            abort(400)
        now = datetime.now(timezone.utc).isoformat()
        merged_settings, transcription_transition = deps["apply_transcription_consent"](current_settings, merged_settings, now)
        merged_settings, voice_transition = deps["apply_voice_consent"](current_settings, merged_settings, now)
        deps["save_user_ai_settings"](user.email, merged_settings)
        if transcription_transition:
            deps["log_security_event"](f"server_transcription_consent_{transcription_transition}", user.email, "Web settings")
        if voice_transition:
            deps["log_security_event"](f"ai_voice_translation_consent_{voice_transition}", user.email, "Web settings")
        return redirect(f"/settings/{user.id}")

    @routes.route("/push-service-worker.js")
    def push_service_worker():
        response = send_from_directory("static", "push-service-worker.js", mimetype="application/javascript")
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Cache-Control"] = "no-cache"
        return response

    return routes
