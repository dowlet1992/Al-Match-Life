from flask import Blueprint, jsonify, redirect, render_template, request, session


def create_ai_core_routes(deps):
    ai_core_routes = Blueprint("ai_core_routes", __name__)

    @ai_core_routes.route("/ai_copilot", methods=["GET", "POST"])
    @ai_core_routes.route("/ai_copilot/<email>", methods=["GET", "POST"])
    def ai_copilot_page(email=None):
        logged_email = session.get("user_email", "")

        if not logged_email:
            return redirect("/")

        user = deps["find_user_by_email"](logged_email)

        if user is None:
            return "User not found"

        if email:
            requested_user = deps["find_user_by_identifier"](email)
            if requested_user is None or deps["normalize_email"](requested_user.email) != deps["normalize_email"](logged_email):
                return redirect(f"/ai_copilot/{deps['safe_text'](user.id)}")

        answer_text = ""
        selected_history = None
        question_value = ""
        selected_mode = "general"
        status = deps["get_ai_provider_status"]()
        if request.method == "POST":
            deps["validate_csrf_token"]()
            if not deps["request_limiter"].allow(f"assistant::{deps['normalize_email'](user.email)}"):
                if request.is_json:
                    response = jsonify({"ok": False, "error": "assistant_rate_limited"})
                    response.status_code = 429
                    response.headers["Retry-After"] = "60"
                    response.headers["Cache-Control"] = "private, no-store"
                    return response
                return "Too many Assistant requests", 429
            payload = request.get_json(silent=True) if request.is_json else request.form
            payload = payload if payload is not None else {}
            question_value = deps["clean_text"](payload.get("question", ""))[:4000]
            selected_mode = deps["clean_text"](payload.get("mode", "general")).strip().lower()
            if selected_mode not in {"general", "profile", "match", "business", "content", "life"}:
                selected_mode = "general"
            if not question_value.strip():
                if request.is_json:
                    return jsonify({"ok": False, "error": "question_required"}), 400
                question_value = ""
            answer = deps["generate_ai_copilot_answer"](user, question_value, selected_mode)
            if question_value.strip() and answer:
                deps["record_ai_core_memory"](user.email, selected_mode, question_value, answer)
            answer_text = deps["clean_text"](answer)
            if request.is_json:
                response = jsonify({
                    "ok": True,
                    "answer": answer_text,
                    "question": deps["safe_text"](question_value),
                    "mode": selected_mode,
                })
                response.headers["Cache-Control"] = "private, no-store"
                return response
        else:
            selected_history = deps["render_selected_ai_core_history"](user.email, request.args.get("history", ""))

        history_items = deps["render_ai_core_history"](user.email, limit=12)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        mode_copy = {
            mode: ui.get(f"ai_mode_{mode}", fallback)
            for mode, fallback in {
                "general": "General", "profile": "Profile", "match": "Connections",
                "business": "Business", "content": "Content", "life": "Life",
            }.items()
        }
        ai_status_text = (
            f"{ui.get('local_model', 'Local model')} · {status.get('model')}"
            if status.get("enabled")
            else ui.get("ai_assistant_unavailable", "AI Assistant is temporarily unavailable")
        )
        return render_template(
            "ai_core.html", ui=ui, title=ui.get("ai_assistant", "AI Assistant"),
            intro=ui.get("ai_core_intro", "The assistant uses your profile, goals, and interests."),
            chat_title=ui.get("ai_core_chat_title", "Conversation"),
            placeholder=ui.get("ai_core_question_placeholder", "Ask a question"),
            submit=ui.get("ai_core_submit", "Send"), status=deps["safe_text"](ai_status_text),
            question=deps["safe_text"](question_value) if question_value else "",
            email=user.email, history_items=history_items, selected_history=selected_history,
            answer_text=answer_text, selected_mode=selected_mode, mode_copy=mode_copy,
            csrf_token_input=deps["csrf_input"](),
        )

    return ai_core_routes
