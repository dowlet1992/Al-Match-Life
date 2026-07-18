from flask import Blueprint, jsonify, request, session

from backend.i18n import (
    SUPPORTED_LANGUAGES,
    build_locale_payload,
    normalize_requested_language_code,
    translation_bundle,
)


def create_i18n_api():
    i18n_api = Blueprint("i18n_api", __name__)

    @i18n_api.route("/api/i18n")
    def api_i18n():
        requested_language = request.args.get("lang", "")
        session_language = "" if requested_language else session.get("language", "")
        locale = build_locale_payload(
            accept_language_header=request.headers.get("Accept-Language", ""),
            requested_language=requested_language,
            user_language=session_language,
        )

        return jsonify({
            "ok": True,
            "locale": locale,
            "translations": translation_bundle(locale["language"]),
        })

    @i18n_api.route("/api/i18n/language", methods=["POST"])
    def api_set_language():
        data = request.get_json(silent=True) or {}
        language_code = normalize_requested_language_code(data.get("language", ""))

        if language_code not in SUPPORTED_LANGUAGES:
            locale = build_locale_payload(
                accept_language_header=request.headers.get("Accept-Language", ""),
                requested_language=language_code,
            )
            return jsonify({
                "ok": False,
                "error": "language_not_supported",
                "message": "This language is recognized but not ready as a production UI language yet.",
                "locale": locale,
            }), 400

        session["language"] = language_code
        session.modified = True
        locale = build_locale_payload(requested_language=language_code)

        return jsonify({
            "ok": True,
            "saved": True,
            "locale": locale,
            "translations": translation_bundle(locale["language"]),
        })

    return i18n_api
