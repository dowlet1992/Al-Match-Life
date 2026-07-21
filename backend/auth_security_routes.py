from datetime import datetime

from flask import Blueprint, redirect, request, session


def create_auth_security_routes(deps):
    auth_security_routes = Blueprint("auth_security_routes", __name__)

    @auth_security_routes.route("/verify_login_2fa", methods=["GET", "POST"])
    def verify_login_2fa():
        pending_email = session.get("pending_2fa_email", "") or request.values.get("email", "")
        contact_type = session.get("pending_2fa_contact_type", "email") or request.values.get("contact_type", "email")
        contact_value = session.get("pending_2fa_contact_value", "") or request.values.get("contact_value", "")
        message = ""

        pending_email = deps["normalize_email"](pending_email)
        contact_type = deps["clean_text"](contact_type).lower()
        if contact_type == "phone":
            contact_value = deps["normalize_phone"](contact_value)
        else:
            contact_value = deps["normalize_email"](contact_value)

        if pending_email and contact_value:
            session.permanent = True
            session["pending_2fa_email"] = pending_email
            session["pending_2fa_contact_type"] = contact_type
            session["pending_2fa_contact_value"] = contact_value
            session.modified = True

        if not pending_email or not contact_value:
            deps["log_security_event"]("login_2fa_session_missing", "", "pending 2FA session is missing")
            return "Сессия подтверждения входа не найдена. Вернитесь на главную страницу и войдите заново.", 400

        user = deps["find_user_by_email"](pending_email)
        if user is None:
            session.clear()
            return "Пользователь для подтверждения входа не найден. Войдите заново.", 400

        if request.method == "POST":
            deps["validate_csrf_token"]()
            code = request.form.get("code", "")

            if deps["verify_contact_code"]("login_2fa", contact_type, contact_value, code):
                csrf_token = session.get("csrf_token")
                session_language = session.get("language")
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
                deps["log_security_event"]("login_2fa_success", user.email, f"via={contact_type}")
                deps["record_trusted_device_seen"](user)
                deps["send_login_alert"](user)
                return redirect(deps["onboarding_redirect_for"](user), code=303)

            deps["log_security_event"]("login_2fa_failed", user.email, f"via={contact_type}")
            message = "Неверный или просроченный код."

        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Подтверждение входа</title>
            {deps["page_style"]()}
        </head>
        <body>
            <div class="card">
                <h1>🔐 Подтверждение входа</h1>
                <p>Введите 6-значный код безопасности.</p>
                <p style="color:#94a3b8;">Код отправлен через: {deps["safe_text"](contact_type)}</p>
                <p style="color:#facc15;">{deps["safe_text"](message)}</p>

                <form method="POST">
                    {deps["csrf_input"]()}
                    <input name="code" placeholder="6-значный код" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                    <button type="submit">Подтвердить вход</button>
                </form>

                <button class="back" onclick="window.location.href='/cancel_login_2fa'">Отмена</button>
            </div>
        </body>
        </html>
        """

    @auth_security_routes.route("/cancel_login_2fa")
    def cancel_login_2fa():
        session.clear()
        return redirect("/")

    @auth_security_routes.route("/forgot_password", methods=["GET", "POST"])
    def forgot_password():
        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            contact_type = deps["clean_text"](request.form.get("contact_type", "email")).lower()
            contact_value = request.form.get("contact_value", "")

            user = deps["find_user_by_contact"](contact_type, contact_value)

            if user is not None:
                code = deps["create_verification_code"]("password_reset", contact_type, contact_value)
                if code:
                    deps["send_verification_code"](contact_type, contact_value, code)
                    deps["log_security_event"]("password_reset_code_sent", getattr(user, "email", ""), f"via={contact_type}")

            message = "Если аккаунт найден, код восстановления отправлен. Проверьте email/SMS или терминал в режиме разработки."

        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Восстановление пароля</title>
            {deps["page_style"]()}
        </head>
        <body>
            <div class="card">
                <h1>🔐 Восстановление пароля</h1>
                <p>Выберите способ восстановления: email или телефон.</p>
                <p style="color:#22c55e;">{deps["safe_text"](message)}</p>

                <form method="POST">
                    {deps["csrf_input"]()}
                    <select name="contact_type" style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;">
                        <option value="email">Email</option>
                        <option value="phone">Телефон</option>
                    </select>
                    <input name="contact_value" placeholder="Email или номер телефона" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                    <button type="submit">Получить код</button>
                </form>

                <button class="back" onclick="window.location.href='/reset_password'">У меня уже есть код</button>
                <button class="back" onclick="window.location.href='/'">Назад</button>
            </div>
        </body>
        </html>
        """

    @auth_security_routes.route("/reset_password", methods=["GET", "POST"])
    def reset_password():
        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            contact_type = deps["clean_text"](request.form.get("contact_type", "email")).lower()
            contact_value = request.form.get("contact_value", "")
            code = request.form.get("code", "")
            new_password = request.form.get("new_password", "")

            user = deps["find_user_by_contact"](contact_type, contact_value)

            if user is None:
                message = "Неверный код или аккаунт не найден."
            elif len(new_password) < 8:
                message = "Пароль должен быть минимум 8 символов."
            elif deps["verify_contact_code"]("password_reset", contact_type, contact_value, code):
                deps["set_user_password"](user, new_password)
                deps["save_users_to_json"](deps["get_users"]())
                deps["clear_login_attempts"](getattr(user, "email", ""))
                deps["log_security_event"]("password_reset_success", getattr(user, "email", ""), f"via={contact_type}")
                message = "Пароль успешно изменён. Теперь можно войти."
            else:
                deps["log_security_event"]("password_reset_failed", contact_value, f"via={contact_type}")
                message = "Неверный или просроченный код."

        return f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Новый пароль</title>
            {deps["page_style"]()}
        </head>
        <body>
            <div class="card">
                <h1>🔑 Новый пароль</h1>
                <p style="color:#facc15;">{deps["safe_text"](message)}</p>

                <form method="POST">
                    {deps["csrf_input"]()}
                    <select name="contact_type" style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;">
                        <option value="email">Email</option>
                        <option value="phone">Телефон</option>
                    </select>
                    <input name="contact_value" placeholder="Email или номер телефона" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                    <input name="code" placeholder="6-значный код" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                    <input name="new_password" type="password" placeholder="Новый пароль" required style="width:100%;padding:12px;border-radius:10px;margin-bottom:12px;box-sizing:border-box;">
                    <button type="submit">Сменить пароль</button>
                </form>

                <button class="back" onclick="window.location.href='/forgot_password'">Получить новый код</button>
                <button class="back" onclick="window.location.href='/'">Назад</button>
            </div>
        </body>
        </html>
        """

    @auth_security_routes.route("/logout", methods=["POST"])
    @deps["login_required"]
    def logout():
        deps["validate_csrf_token"]()
        session.clear()
        return redirect("/")

    return auth_security_routes
