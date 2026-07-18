from flask import Blueprint, redirect, request, session


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

        if email and deps["normalize_email"](email) != deps["normalize_email"](logged_email):
            return redirect(f"/ai_copilot/{deps['safe_text'](user.email)}")

        answer_html = ""
        question_value = ""
        selected_mode = "general"
        status = deps["get_openai_status"]()
        ai_status_text = (
            f"Real AI подключён · модель: {status.get('model')}"
            if status.get("enabled")
            else "AI Core в резервном режиме · добавьте OPENAI_API_KEY в .env"
        )

        if request.method == "POST":
            deps["validate_csrf_token"]()
            question_value = deps["clean_text"](request.form.get("question", ""))
            answer = deps["generate_ai_copilot_answer"](user, question_value, selected_mode)
            deps["record_ai_core_memory"](user.email, selected_mode, question_value, answer)
            answer_html = f"""
            <div style="background:#0f172a;border:1px solid rgba(96,165,250,0.22);border-radius:24px;padding:22px;margin-top:18px;">
                <h2 style="margin:0 0 12px 0;color:#bfdbfe;">Ответ AI Core</h2>
                <div style="line-height:1.7;color:#dbeafe;font-size:16px;">{deps["render_ai_text"](answer)}</div>
            </div>
            """
        else:
            answer_html = deps["render_selected_ai_core_history"](user.email, request.args.get("history", ""))

        history_html = deps["render_ai_core_history"](user.email, limit=12)

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AI Core - AI Match Life</title>
        </head>
        <body style="margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;">
            <div style="max-width:980px;margin:auto;">
                <a href="/dashboard/{deps["safe_text"](user.email)}" style="display:inline-block;color:white;text-decoration:none;background:#334155;padding:12px 16px;border-radius:14px;margin-bottom:18px;font-weight:bold;">← Назад</a>

                <div style="background:linear-gradient(135deg,#1e293b,#172554);padding:30px;border-radius:30px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.14);">
                    <h1 style="margin:0 0 10px 0;font-size:34px;">🧠 AI Core</h1>
                    <p style="margin:0;color:#cbd5e1;line-height:1.55;">Внутренний AI-ассистент AI Match Life. Он использует профиль, цели, интересы и AI Discover learning, чтобы помогать пользователю умнее.</p>
                    <div style="display:inline-flex;margin-top:16px;background:rgba(15,23,42,0.55);border:1px solid rgba(96,165,250,0.26);border-radius:999px;padding:9px 13px;color:#bfdbfe;font-weight:bold;font-size:13px;">{deps["safe_text"](ai_status_text)}</div>
                </div>

                <div style="display:grid;grid-template-columns:minmax(230px,300px) minmax(0,1fr);gap:18px;align-items:start;">
                    {history_html}

                    <main>
                        <div style="background:#1e293b;padding:22px;border-radius:26px;border:1px solid rgba(148,163,184,0.10);">
                            <h2 style="margin:0 0 14px 0;font-size:20px;">💬 AI Chat</h2>

                            <form method="POST">
                                {deps["csrf_input"]()}
                                <input type="hidden" name="mode" value="general">
                                <textarea name="question" required placeholder="..." style="width:100%;min-height:150px;background:#0f172a;color:white;border:1px solid #334155;border-radius:18px;padding:14px;box-sizing:border-box;line-height:1.5;">{deps["safe_text"](question_value) if question_value else ''}</textarea>
                                <button type="submit" style="margin-top:14px;background:#2563eb;color:white;border:none;border-radius:16px;padding:14px 18px;font-weight:bold;cursor:pointer;width:100%;">Отправить в AI Core</button>
                            </form>
                        </div>

                        {answer_html}
                    </main>
                </div>
            </div>
        </body>
        </html>
        """

    return ai_core_routes
