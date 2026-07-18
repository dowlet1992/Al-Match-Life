from flask import Blueprint, jsonify


def create_matches_api(deps):
    matches_api = Blueprint("matches_api", __name__)

    def api_error(message, status_code=400):
        response = jsonify({
            "ok": False,
            "error": deps["clean_text"](message),
        })
        response.status_code = status_code
        return response

    @matches_api.route("/api/matches")
    def api_matches():
        current_user = deps["get_api_current_user"]()
        if current_user is None:
            return api_error("Authentication required", 401)

        results = []

        for match in deps["find_best_matches"](current_user, deps["get_users"]()):
            matched_user = match["user"]
            if not deps["can_show_user_in_ai_recommendations"](current_user.email, matched_user):
                continue

            score = match["score"]
            results.append({
                "user": deps["api_user_payload"](matched_user),
                "score": score,
                "level": deps["get_match_level"](score),
                "reasons": [
                    deps["clean_text"](reason)
                    for reason in deps["explain_match"](current_user, matched_user)
                ],
            })

        return jsonify({
            "ok": True,
            "matches": results,
        })

    return matches_api
