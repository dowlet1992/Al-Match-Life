from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request


ALLOWED_PROOF_TYPES = {"video", "photo", "document", "project", "achievement"}
ALLOWED_PRIVACY_SETTINGS = {
    "receive_recommendations", "show_me_to_others", "show_in_search",
    "allow_messages", "verified_only_messages", "vip_mode",
}


def create_proof_privacy_routes(deps):
    routes = Blueprint("proof_privacy_routes", __name__)

    @routes.route("/proof/<viewer_email>/<profile_email>")
    def proof_profile_page(viewer_email, profile_email):
        profile_user = deps["find_user_by_email"](profile_email)
        viewer_user = deps["find_user_by_email"](viewer_email)
        if profile_user is None:
            return "User not found", 404

        ui = deps["translation_bundle"](deps["get_current_language"](viewer_user or profile_user))
        proofs = deps["load_proofs"]().get("proofs", [])
        proofs = proofs if isinstance(proofs, list) else []
        counts = {key: 0 for key in ALLOWED_PROOF_TYPES}
        for proof in proofs:
            if not isinstance(proof, dict) or deps["normalize_email"](proof.get("email", "")) != deps["normalize_email"](profile_user.email):
                continue
            proof_type = "document" if proof.get("type") == "certificate" else proof.get("type")
            if proof_type in counts:
                counts[proof_type] += 1

        proof_score = min(100, counts["document"] * 15 + counts["project"] * 20 + counts["video"] * 20 + counts["achievement"] * 15)
        total_proofs = sum(counts.values())
        proof_summary = ui.get("proof_summary", "This user uploaded {total} proofs of skills, experience, and achievements.").format(total=total_proofs)
        cards = [
            {"type": "video", "icon": "🎥", "title": ui.get("proof_video_title", "Video proofs"), "intro": ui.get("proof_video_intro", ""), "count": counts["video"]},
            {"type": "photo", "icon": "📸", "title": ui.get("proof_photo_title", "Photos and projects"), "intro": ui.get("proof_photo_intro", ""), "count": counts["photo"]},
            {"type": "document", "icon": "📄", "title": ui.get("proof_documents_title", "Documents"), "intro": ui.get("proof_documents_intro", ""), "count": counts["document"]},
            {"type": "project", "icon": "🚀", "title": ui.get("proof_projects_title", "Projects"), "intro": ui.get("proof_projects_intro", ""), "count": counts["project"]},
            {"type": "achievement", "icon": "🏅", "title": ui.get("proof_achievements_title", "Achievements"), "intro": ui.get("proof_achievements_intro", ""), "count": counts["achievement"]},
        ]
        language = ui.get("language_code", "en")
        page_copy = {
            "ru": {"title": "Proof Profile", "trust": "Доверие к профилю", "summary": "Сводка доверия"},
            "de": {"title": "Proof Profile", "trust": "Profilvertrauen", "summary": "Vertrauensübersicht"},
            "en": {"title": "Proof Profile", "trust": "Profile trust", "summary": "Trust summary"},
            "tr": {"title": "Proof Profile", "trust": "Profil güveni", "summary": "Güven özeti"},
        }.get(language, {"title": "Proof Profile", "trust": "Profile trust", "summary": "Trust summary"})
        authenticated_email = deps["normalize_email"](deps["current_session_email"]())
        return render_template(
            "proof_profile.html", email=authenticated_email or None, profile_email=profile_user.email,
            viewer_email=viewer_email, ui=ui, copy=page_copy, cards=cards,
            can_add=authenticated_email == deps["normalize_email"](profile_user.email),
            proof_score=proof_score, total_proofs=total_proofs, proof_summary=proof_summary,
        )

    @routes.route("/add_proof/<viewer_email>/<profile_email>/<proof_type>", methods=["GET", "POST"])
    def add_proof_page(viewer_email, profile_email, proof_type):
        profile_user = deps["find_user_by_email"](profile_email)
        viewer_user = deps["find_user_by_email"](viewer_email)
        if profile_user is None:
            return "User not found", 404
        if proof_type not in ALLOWED_PROOF_TYPES:
            abort(404)
        ui = deps["translation_bundle"](deps["get_current_language"](viewer_user or profile_user))
        if request.method == "POST":
            deps["validate_csrf_token"]()
            if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](profile_user.email):
                abort(403)
            title = deps["clean_text"](request.form.get("title", ""))[:120]
            description = deps["clean_text"](request.form.get("description", ""))[:2000]
            if not title or not description:
                abort(400)
            data = deps["load_proofs"]()
            proofs = data.get("proofs", [])
            proofs = proofs if isinstance(proofs, list) else []
            proofs.append({"email": profile_user.email, "type": proof_type, "title": title, "description": description, "date": datetime.now().strftime("%d.%m.%Y %H:%M")})
            data["proofs"] = proofs
            deps["save_proofs"](data)
            return redirect(f"/proof/{viewer_email}/{profile_email}", code=303)
        return render_template(
            "add_proof.html", ui=ui, email=deps["normalize_email"](deps["current_session_email"]()) or None,
            viewer_email=viewer_email, profile_email=profile_email, proof_type=proof_type,
            csrf_token_input=deps["csrf_input"](),
        )

    @routes.route("/privacy/<email>")
    @deps["login_required"]
    def privacy_page(email):
        user = deps["find_user_by_email"](email)
        if user is None:
            return "User not found", 404
        ui = deps["translation_bundle"](deps["get_current_language"](user))
        settings = deps["get_user_privacy"](email)
        controls = [
            ("receive_recommendations", "receive_recommendations", "receive_recommendations_help"),
            ("show_me_to_others", "recommend_my_profile", "recommend_my_profile_help"),
            ("show_in_search", "show_in_search", "show_in_search_help"),
            ("allow_messages", "allow_messages", "allow_messages_help"),
            ("verified_only_messages", "verified_only", "verified_only_help"),
            ("vip_mode", "vip_private_mode", "vip_private_mode_help"),
        ]
        privacy_controls = [{"setting": setting, "label": ui.get(label, label.replace("_", " ").title()), "help": ui.get(help, ""), "enabled": bool(settings.get(setting, False))} for setting, label, help in controls]
        return render_template("privacy.html", email=user.email, ui=ui, privacy_controls=privacy_controls, csrf_token_input=deps["csrf_input"]())

    @routes.route("/toggle_privacy/<email>/<setting>", methods=["POST"])
    @deps["login_required"]
    def toggle_privacy(email, setting):
        deps["validate_csrf_token"]()
        if setting not in ALLOWED_PRIVACY_SETTINGS:
            abort(404)
        settings = deps["get_user_privacy"](email)
        deps["update_user_privacy"](email, setting, not settings.get(setting, False))
        return redirect(f"/privacy/{email}")

    return routes
