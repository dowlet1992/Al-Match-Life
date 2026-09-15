from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session


def create_auth_security_routes(deps):
    auth_security_routes = Blueprint("auth_security_routes", __name__)

    def localized_copy():
        ui = deps["translation_bundle"](deps["get_current_language"]())
        language = ui.get("language_code", "en")
        values = {
            "ru": {
                "login_verify": "Подтверждение входа", "login_intro": "Введите 6-значный код безопасности.",
                "confirm": "Подтвердить вход", "cancel": "Отмена", "forgot": "Восстановление пароля",
                "forgot_intro": "Выберите способ восстановления: email или телефон.", "phone": "Телефон",
                "contact": "Email или номер телефона", "send": "Получить код", "have_code": "У меня уже есть код",
                "new_password": "Новый пароль", "change": "Сменить пароль", "new_code": "Получить новый код", "back": "Назад",
                "code": "6-значный код",
                "invalid_code": "Неверный или просроченный код.",
                "session_missing": "Сессия подтверждения входа не найдена. Вернитесь на главную страницу и войдите заново.",
                "user_missing": "Пользователь для подтверждения входа не найден. Войдите заново.",
                "recovery_sent": "Если аккаунт найден, код восстановления отправлен. Проверьте email или SMS.",
                "reset_account_missing": "Неверный код или аккаунт не найден.", "reset_password_short": "Пароль должен содержать не менее 8 символов.",
                "reset_success": "Пароль успешно изменён. Теперь можно войти.",
            },
            "de": {
                "login_verify": "Anmeldung bestätigen", "login_intro": "Geben Sie den 6-stelligen Sicherheitscode ein.",
                "confirm": "Anmeldung bestätigen", "cancel": "Abbrechen", "forgot": "Passwort wiederherstellen",
                "forgot_intro": "Wählen Sie E-Mail oder Telefon.", "phone": "Telefon",
                "contact": "E-Mail oder Telefonnummer", "send": "Code senden", "have_code": "Ich habe bereits einen Code",
                "new_password": "Neues Passwort", "change": "Passwort ändern", "new_code": "Neuen Code senden", "back": "Zurück",
                "code": "6-stelliger Code",
                "invalid_code": "Der Code ist ungültig oder abgelaufen.",
                "session_missing": "Die Sitzung zur Anmeldebestätigung wurde nicht gefunden. Melden Sie sich erneut an.",
                "user_missing": "Das zu bestätigende Konto wurde nicht gefunden. Melden Sie sich erneut an.",
                "recovery_sent": "Wenn das Konto gefunden wurde, wurde ein Wiederherstellungscode per E-Mail oder SMS gesendet.",
                "reset_account_missing": "Ungültiger Code oder Konto nicht gefunden.", "reset_password_short": "Das Passwort muss mindestens 8 Zeichen lang sein.",
                "reset_success": "Das Passwort wurde geändert. Sie können sich jetzt anmelden.",
            },
            "en": {
                "login_verify": "Confirm sign-in", "login_intro": "Enter the 6-digit security code.",
                "confirm": "Confirm sign-in", "cancel": "Cancel", "forgot": "Password recovery",
                "forgot_intro": "Choose email or phone recovery.", "phone": "Phone",
                "contact": "Email or phone number", "send": "Send code", "have_code": "I already have a code",
                "new_password": "New password", "change": "Change password", "new_code": "Send a new code", "back": "Back",
                "code": "6-digit code",
                "invalid_code": "The code is invalid or expired.",
                "session_missing": "Sign-in verification session was not found. Please sign in again.",
                "user_missing": "The account to verify was not found. Please sign in again.",
                "recovery_sent": "If the account was found, a recovery code was sent by email or SMS.",
                "reset_account_missing": "Invalid code or account not found.", "reset_password_short": "Password must be at least 8 characters.",
                "reset_success": "Password changed successfully. You can now sign in.",
            },
            "tr": {
                "login_verify": "Girişi doğrula", "login_intro": "6 haneli güvenlik kodunu girin.",
                "confirm": "Girişi onayla", "cancel": "İptal", "forgot": "Şifre kurtarma",
                "forgot_intro": "E-posta veya telefon ile kurtarma yöntemini seçin.", "phone": "Telefon",
                "contact": "E-posta veya telefon numarası", "send": "Kod gönder", "have_code": "Kodum zaten var",
                "new_password": "Yeni şifre", "change": "Şifreyi değiştir", "new_code": "Yeni kod gönder", "back": "Geri",
                "code": "6 haneli kod", "invalid_code": "Kod yanlış veya süresi dolmuş.",
                "session_missing": "Giriş doğrulama oturumu bulunamadı. Ana sayfaya dönüp tekrar giriş yapın.",
                "user_missing": "Doğrulanacak kullanıcı bulunamadı. Tekrar giriş yapın.",
                "recovery_sent": "Hesap bulunduysa kurtarma kodu e-posta veya SMS ile gönderildi.",
                "reset_account_missing": "Kod geçersiz veya hesap bulunamadı.", "reset_password_short": "Şifre en az 8 karakter olmalıdır.",
                "reset_success": "Şifre başarıyla değiştirildi. Şimdi giriş yapabilirsiniz.",
            },
        }
        return ui, values.get(language, values["en"])

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

        ui, copy = localized_copy()
        if not pending_email or not contact_value:
            deps["log_security_event"]("login_2fa_session_missing", "", "pending 2FA session is missing")
            return copy.get("session_missing", "Sign-in verification session was not found. Please sign in again."), 400

        user = deps["find_user_by_email"](pending_email)
        if user is None:
            session.clear()
            return copy.get("user_missing", "The account to verify was not found. Please sign in again."), 400

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
            message = copy.get("invalid_code", "The code is invalid or expired.")

        return render_template(
            "auth_verify.html", ui=ui, icon="🔐", title=copy["login_verify"],
            intro=copy["login_intro"], method=f'{contact_type}', message=message,
            contact_type="", contact_value="", code_placeholder=copy["code"],
            confirm=copy["confirm"], cancel=copy["cancel"], cancel_url="/cancel_login_2fa",
            csrf_token_input=deps["csrf_input"](),
        )

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

            _, copy = localized_copy()
            message = copy["recovery_sent"]

        ui, copy = localized_copy()
        return render_template(
            "auth_recovery.html", ui=ui, icon="🔐", title=copy["forgot"],
            intro=copy["forgot_intro"], message=message, reset_mode=False,
            method_label=copy["forgot_intro"], phone_label=copy["phone"],
            contact_placeholder=copy["contact"], submit_label=copy["send"],
            alternate_url="/reset_password", alternate_label=copy["have_code"],
            back_label=copy["back"], csrf_token_input=deps["csrf_input"](),
        )

    @auth_security_routes.route("/reset_password", methods=["GET", "POST"])
    def reset_password():
        message = ""
        ui, copy = localized_copy()

        if request.method == "POST":
            deps["validate_csrf_token"]()
            contact_type = deps["clean_text"](request.form.get("contact_type", "email")).lower()
            contact_value = request.form.get("contact_value", "")
            code = request.form.get("code", "")
            new_password = request.form.get("new_password", "")

            user = deps["find_user_by_contact"](contact_type, contact_value)

            if user is None:
                message = copy["reset_account_missing"]
            elif len(new_password) < 8:
                message = copy["reset_password_short"]
            elif deps["verify_contact_code"]("password_reset", contact_type, contact_value, code):
                deps["set_user_password"](user, new_password)
                deps["save_users_to_json"](deps["get_users"]())
                deps["clear_login_attempts"](getattr(user, "email", ""))
                deps["log_security_event"]("password_reset_success", getattr(user, "email", ""), f"via={contact_type}")
                message = copy["reset_success"]
            else:
                deps["log_security_event"]("password_reset_failed", contact_value, f"via={contact_type}")
                message = copy["invalid_code"]

        return render_template(
            "auth_recovery.html", ui=ui, icon="🔑", title=copy["new_password"],
            intro="", message=message, reset_mode=True,
            method_label=copy["forgot_intro"], phone_label=copy["phone"],
            contact_placeholder=copy["contact"], code_placeholder=copy["code"],
            password_placeholder=copy["new_password"], submit_label=copy["change"],
            alternate_url="/forgot_password", alternate_label=copy["new_code"],
            back_label=copy["back"], csrf_token_input=deps["csrf_input"](),
        )

    @auth_security_routes.route("/logout", methods=["POST"])
    @deps["login_required"]
    def logout():
        deps["validate_csrf_token"]()
        session.clear()
        return redirect("/")

    return auth_security_routes
