import json
import urllib.parse
from datetime import datetime

from flask import Blueprint, abort, redirect, request, session


def create_settings_security_blueprint(deps):
    settings_security = Blueprint("settings_security", __name__)

    @settings_security.route("/settings/<email>/security_activity")
    @deps["login_required"]
    def settings_security_activity(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            deps["log_security_event"](
                "security_activity_denied",
                deps["current_session_email"](),
                f"target={user.email}",
            )
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        events = deps["user_security_events"](user.email, limit=40)
        rows_html = ""

        for event in events:
            display = deps["security_event_display"](event, ui)
            rows_html += f"""
            <article class="row-card security-event security-event-{deps["safe_text"](display["tone"])}">
                <div>
                    <span class="event-badge">{deps["safe_text"](display["category"])}</span>
                    <strong>{deps["safe_text"](display["title"])}</strong>
                    <p>{deps["safe_text"](display["details"])}</p>
                </div>
                <div class="muted-card" style="min-width:160px;text-align:right;">
                    <span>{deps["safe_text"](display["time"])}</span>
                    <span>{deps["safe_text"](display["ip"])}</span>
                </div>
            </article>
            """

        if rows_html == "":
            rows_html = f"""
            <div class="empty-state">
                {deps["safe_text"](ui.get("security_activity_empty", "No security activity yet."))}
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{deps["safe_text"](ui.get('security_activity_title', 'Security activity'))} - AI Match Life</title>
            {deps["settings_control_css"]("920px")}
            <style>
                .security-event{{position:relative;overflow:hidden;}}
                .security-event::before{{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:#60a5fa;}}
                .security-event-good::before{{background:#22c55e;}}
                .security-event-warning::before{{background:#f59e0b;}}
                .security-event-danger::before{{background:#ef4444;}}
                .event-badge{{display:inline-flex;margin-bottom:8px;border-radius:999px;padding:5px 9px;background:rgba(96,165,250,0.16);border:1px solid rgba(147,197,253,0.24);color:#bfdbfe;font-size:12px;font-weight:900;}}
                .security-event-good .event-badge{{background:rgba(34,197,94,0.14);border-color:rgba(74,222,128,0.24);color:#bbf7d0;}}
                .security-event-warning .event-badge{{background:rgba(245,158,11,0.14);border-color:rgba(251,191,36,0.24);color:#fde68a;}}
                .security-event-danger .event-badge{{background:rgba(239,68,68,0.14);border-color:rgba(248,113,113,0.24);color:#fecaca;}}
            </style>
        </head>
        <body>
            <main class="page">
                <a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
                <section class="hero">
                    <h1>{deps["safe_text"](ui.get('security_activity_title', 'Security activity'))}</h1>
                    <p>{deps["safe_text"](ui.get('security_activity_intro', 'Review recent login and security events for your account.'))}</p>
                </section>
                {rows_html}
            </main>
        </body>
        </html>
        """

    @settings_security.route("/settings/<email>/data_export")
    @deps["login_required"]
    def settings_data_export(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            deps["log_security_event"](
                "data_export_denied",
                deps["current_session_email"](),
                f"target={user.email}",
            )
            abort(403)

        normalized_email = deps["normalize_email"](user.email)
        feed_data = deps["load_feed"]()
        posts = feed_data.get("posts", []) if isinstance(feed_data, dict) else []
        messages = deps["load_messages"]()

        export_data = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account": deps["safe_account_payload"](user),
            "settings": deps["normalize_user_ai_settings"](user.email),
            "notifications": deps["get_notifications"](user.email),
            "posts": [
                post for post in posts
                if isinstance(post, dict) and deps["normalize_email"](post.get("email", post.get("author_email", ""))) == normalized_email
            ],
            "messages": [
                message for message in messages
                if isinstance(message, dict)
                and normalized_email in {
                    deps["normalize_email"](message.get("from", "")),
                    deps["normalize_email"](message.get("to", "")),
                }
            ] if isinstance(messages, list) else [],
            "security_events": deps["user_security_events"](user.email, limit=100),
        }

        deps["log_security_event"]("data_export_created", user.email, "User downloaded account data export")
        payload = json.dumps(export_data, ensure_ascii=False, indent=2)
        response = deps["response_class"](payload, mimetype="application/json; charset=utf-8")
        response.headers["Content-Disposition"] = f'attachment; filename="ai-match-life-{normalized_email}-export.json"'
        return response

    @settings_security.route("/settings/<email>/password", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_change_password(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            deps["log_security_event"](
                "password_change_denied",
                deps["current_session_email"](),
                f"target={user.email}",
            )
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        message = ""
        message_color = "#facc15"
        requires_security_code = deps["user_requires_sensitive_action_2fa"](user)

        if request.method == "POST":
            deps["validate_csrf_token"]()
            action = request.form.get("action", "change_password")
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            confirmation_code = request.form.get("confirmation_code", "")

            if not deps["verify_user_password"](user, current_password):
                message = ui.get("current_password_invalid", "Current password is incorrect.")
                deps["log_security_event"]("password_change_failed", user.email, "current_password_invalid")
            elif action == "send_security_code":
                if deps["send_sensitive_action_code"](user, "sensitive_password_change"):
                    message = ui.get("security_code_sent", "Security code sent.")
                    message_color = "#22c55e"
                else:
                    message = ui.get("security_code_send_failed", "Could not send security code yet. Please wait and try again.")
                    deps["log_security_event"]("sensitive_action_code_send_failed", user.email, "purpose=sensitive_password_change")
            elif len(new_password) < 8:
                message = ui.get("new_password_too_short", "New password must be at least 8 characters.")
            elif new_password != confirm_password:
                message = ui.get("new_passwords_do_not_match", "New passwords do not match.")
            elif not deps["verify_sensitive_action_code"](user, "sensitive_password_change", confirmation_code):
                message = ui.get("security_code_invalid", "Security code is invalid or expired.")
                deps["log_security_event"]("password_change_failed", user.email, "security_code_invalid")
            else:
                deps["set_user_password"](user, new_password)
                deps["save_users_to_json"](deps["get_users"]())
                deps["clear_login_attempts"](user.email)
                deps["log_security_event"]("password_changed", user.email, "User changed password from settings")
                message = ui.get("password_changed_success", "Password changed successfully.")
                message_color = "#22c55e"

        return f"""
        <!DOCTYPE html>
        <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{deps["safe_text"](ui.get('change_password_title', 'Change password'))} - AI Match Life</title>
            {deps["settings_control_css"]("620px")}
        </head>
        <body>
            <main class="page">
                <a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
                <section class="hero">
                    <h1>{deps["safe_text"](ui.get('change_password_title', 'Change password'))}</h1>
                    <p>{deps["safe_text"](ui.get('change_password_intro', 'For security, enter your current password first, then your new password.'))}</p>
                    <p class="message" style="color:{message_color};">{deps["safe_text"](message)}</p>
                </section>
                <section class="card">
                    <form method="POST">
                        {deps["csrf_input"]()}
                        <label>{deps["safe_text"](ui.get('current_password', 'Current password'))}</label>
                        <input type="password" name="current_password" autocomplete="current-password" required>
                        <label>{deps["safe_text"](ui.get('new_password', 'New password'))}</label>
                        <input type="password" name="new_password" autocomplete="new-password" minlength="8" required>
                        <label>{deps["safe_text"](ui.get('confirm_new_password', 'Confirm new password'))}</label>
                        <input type="password" name="confirm_password" autocomplete="new-password" minlength="8" required>
                        {f'''
                        <label>{deps["safe_text"](ui.get('sensitive_action_code', 'Security code'))}</label>
                        <input name="confirmation_code" inputmode="numeric" autocomplete="one-time-code" placeholder="{deps["safe_text"](ui.get('sensitive_action_code_placeholder', '6-digit code'))}">
                        <button type="submit" name="action" value="send_security_code" formnovalidate>{deps["safe_text"](ui.get('send_security_code', 'Send security code'))}</button>
                        ''' if requires_security_code else ''}
                        <button type="submit" name="action" value="change_password">{deps["safe_text"](ui.get('change_password', 'Change password'))}</button>
                    </form>
                </section>
            </main>
        </body>
        </html>
        """

    @settings_security.route("/settings/<email>/email_phone", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_email_phone(email):
        user = deps["find_user_by_email"](email)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.email):
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        message = ""
        message_color = "#facc15"
        pending = session.get("pending_contact_change", {}) if isinstance(session.get("pending_contact_change"), dict) else {}

        if request.method == "POST":
            deps["validate_csrf_token"]()
            action = request.form.get("action", "send")
            current_password = request.form.get("current_password", "")

            if action == "send":
                new_email = deps["normalize_email"](request.form.get("new_email", ""))
                new_phone = deps["normalize_phone"](request.form.get("new_phone", ""))
                contact_type = "email" if new_email else "phone"
                contact_value = new_email or new_phone

                if not deps["verify_user_password"](user, current_password):
                    message = ui.get("current_password_invalid", "Current password is incorrect.")
                elif not contact_value:
                    message = ui.get("contact_value_required", "Enter a new email or phone.")
                elif deps["find_user_by_contact"](contact_type, contact_value) is not None:
                    message = ui.get("contact_already_used", "This contact is already in use.")
                else:
                    code = deps["create_verification_code"]("contact_change", contact_type, contact_value)
                    deps["send_verification_code"](contact_type, contact_value, code)
                    pending = {"type": contact_type, "value": contact_value, "old_email": user.email}
                    session["pending_contact_change"] = pending
                    message = ui.get("contact_code_sent", "Confirmation code sent.")

            elif action == "confirm":
                code = request.form.get("confirmation_code", "")
                contact_type = pending.get("type", "")
                contact_value = pending.get("value", "")
                if not contact_type or not contact_value or not deps["verify_contact_code"]("contact_change", contact_type, contact_value, code):
                    message = ui.get("confirmation_code_invalid", "Confirmation code is invalid or expired.")
                else:
                    old_email = user.email
                    if contact_type == "email":
                        user.email = deps["normalize_email"](contact_value)
                        session["user_email"] = user.email
                        deps["migrate_user_settings_email"](old_email, user.email)
                    else:
                        user.phone = deps["normalize_phone"](contact_value)
                    deps["save_users_to_json"](deps["get_users"]())
                    session.pop("pending_contact_change", None)
                    deps["log_security_event"]("contact_changed", user.email, f"type={contact_type}")
                    message = ui.get("contact_updated_success", "Contact details updated.")
                    message_color = "#22c55e"

        pending_text = f"{deps['safe_text'](pending.get('type', ''))}: {deps['safe_text'](pending.get('value', ''))}" if pending else ""
        return f"""
        <!DOCTYPE html>
        <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head>
            <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{deps["safe_text"](ui.get('email_phone_title', 'Email and phone'))} - AI Match Life</title>
            {deps["settings_control_css"]("720px")}
        </head>
        <body><main class="page">
            <a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
            <section class="hero">
                <h1>{deps["safe_text"](ui.get('email_phone_title', 'Email and phone'))}</h1>
                <p>{deps["safe_text"](ui.get('email_phone_intro', 'Change your email or phone only after code confirmation.'))}</p>
                <p class="message" style="color:{message_color};">{deps["safe_text"](message)}</p>
            </section>
            <section class="card">
                <form method="POST">
                    {deps["csrf_input"]()}
                    <input type="hidden" name="action" value="send">
                    <label>{deps["safe_text"](ui.get('current_password', 'Current password'))}</label>
                    <input type="password" name="current_password" autocomplete="current-password" required>
                    <div class="two-column">
                        <div>
                            <label>{deps["safe_text"](ui.get('new_email', 'New email'))}</label>
                            <input type="email" name="new_email" autocomplete="email">
                        </div>
                        <div>
                            <label>{deps["safe_text"](ui.get('new_phone', 'New phone'))}</label>
                            <input type="tel" name="new_phone" autocomplete="tel">
                        </div>
                    </div>
                    <button type="submit">{deps["safe_text"](ui.get('send_confirmation_code', 'Send confirmation code'))}</button>
                </form>
            </section>
            <section class="card">
                <h2>{deps["safe_text"](ui.get('confirm_change', 'Confirm change'))}</h2>
                <p>{pending_text}</p>
                <form method="POST">
                    {deps["csrf_input"]()}
                    <input type="hidden" name="action" value="confirm">
                    <label>{deps["safe_text"](ui.get('confirmation_code', 'Confirmation code'))}</label>
                    <input name="confirmation_code" inputmode="numeric" required>
                    <button type="submit">{deps["safe_text"](ui.get('confirm_change', 'Confirm change'))}</button>
                </form>
            </section>
        </main></body></html>
        """

    @settings_security.route("/settings/<email>/devices")
    @deps["login_required"]
    def settings_devices(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            deps["log_security_event"](
                "devices_page_denied",
                deps["current_session_email"](),
                f"target={user.email}",
            )
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        message_key = deps["clean_text"](request.args.get("message", ""))
        message = ui.get(message_key, "") if message_key else ""
        login_time = session.get("login_time", "")
        ip_address = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        user_agent = deps["clean_text"](request.headers.get("User-Agent", ""))
        device_label = user_agent[:140] if user_agent else "Browser session"
        raw_settings = deps["repository_load_user_ai_settings"](user.email)
        trusted_devices = raw_settings.get("trusted_devices", []) if isinstance(raw_settings, dict) else []
        current_device_id = deps["current_device_fingerprint"]()
        current_device_trusted = any(
            device.get("id") == current_device_id
            for device in trusted_devices
            if isinstance(device, dict)
        )
        trust_status = (
            ui.get("trusted_device_yes", "This is a trusted device")
            if current_device_trusted
            else ui.get("trusted_device_no", "This device is not trusted yet")
        )
        session_events = [
            event for event in deps["user_security_events"](user.email, limit=12)
            if event.get("event") in {
                "login_success",
                "login_2fa_required",
                "login_unverified_account",
                "account_reactivated",
                "password_changed",
                "contact_changed",
                "trusted_devices_updated",
                "current_device_signed_out",
                "other_devices_signed_out",
                "stale_session_rejected",
                "stale_api_session_rejected",
            }
        ]
        session_rows_html = ""
        for event in session_events:
            session_rows_html += f"""
            <article class="row-card">
                <div>
                    <strong>{deps["safe_text"](event.get("event", ""))}</strong>
                    <p>{deps["safe_text"](event.get("details", ""))}</p>
                </div>
                <div class="muted-card" style="min-width:160px;text-align:right;">
                    <span>{deps["safe_text"](event.get("time", ""))}</span>
                    <span>{deps["safe_text"](event.get("ip", ""))}</span>
                </div>
            </article>
            """
        if session_rows_html == "":
            session_rows_html = f'<div class="empty-state">{deps["safe_text"](ui.get("recent_session_history_empty", "No session history yet."))}</div>'

        return f"""
        <!DOCTYPE html>
        <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{deps["safe_text"](ui.get('device_sessions_title', 'Devices and sessions'))} - AI Match Life</title>
            {deps["settings_control_css"]("920px")}
            <style>
                .info-grid{{display:grid;grid-template-columns:180px 1fr;gap:10px;margin-top:16px;}}
                .info-label{{color:#93c5fd;font-weight:900;}}
                .info-value{{color:#e5e7eb;word-break:break-word;}}
                .trust-pill{{display:inline-flex;margin-top:14px;border-radius:999px;padding:8px 12px;background:#111827;border:1px solid rgba(96,165,250,0.26);color:#bfdbfe;font-weight:900;}}
                @media(max-width:680px){{.info-grid{{grid-template-columns:1fr}}}}
            </style>
        </head>
        <body>
            <main class="page">
                <a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
                <section class="hero">
                    <h1>{deps["safe_text"](ui.get('device_sessions_title', 'Devices and sessions'))}</h1>
                    <p>{deps["safe_text"](ui.get('device_sessions_intro', 'Review your current active session and manage sign-out for this device.'))}</p>
                </section>
                <section class="card">
                    <h2>{deps["safe_text"](ui.get('current_session', 'Current session'))}</h2>
                    <div class="info-grid">
                        <div class="info-label">{deps["safe_text"](ui.get('signed_in_as', 'Signed in as'))}</div>
                        <div class="info-value">{deps["safe_text"](user.email)}</div>
                        <div class="info-label">{deps["safe_text"](ui.get('login_time_label', 'Login time'))}</div>
                        <div class="info-value">{deps["safe_text"](login_time or '-')}</div>
                        <div class="info-label">{deps["safe_text"](ui.get('ip_address_label', 'IP address'))}</div>
                        <div class="info-value">{deps["safe_text"](ip_address)}</div>
                        <div class="info-label">{deps["safe_text"](ui.get('device_label', 'Device'))}</div>
                        <div class="info-value">{deps["safe_text"](device_label)}</div>
                        <div class="info-label">{deps["safe_text"](ui.get('trusted_device_status', 'Trust status'))}</div>
                        <div class="info-value">{deps["safe_text"](trust_status)}</div>
                    </div>
                    <span class="trust-pill">{deps["safe_text"](trust_status)}</span>
                    <form method="POST" action="/settings/{deps["safe_text"](user.email)}/devices/logout_current">
                        {deps["csrf_input"]()}
                        <button class="danger-button" type="submit">{deps["safe_text"](ui.get('sign_out_this_device', 'Sign out this device'))}</button>
                    </form>
                </section>
                <section class="card">
                    <h2>{deps["safe_text"](ui.get('other_sessions', 'Other devices'))}</h2>
                    <p class="message">{deps["safe_text"](message)}</p>
                    <p>{deps["safe_text"](ui.get('other_sessions_intro', 'Use this if you lost a phone, used a public computer, or see suspicious account activity.'))}</p>
                    <form method="POST" action="/settings/{deps["safe_text"](user.email)}/devices/logout_others">
                        {deps["csrf_input"]()}
                        <label>{deps["safe_text"](ui.get('current_password', 'Current password'))}</label>
                        <input type="password" name="current_password" autocomplete="current-password" required>
                        {f'''
                        <label>{deps["safe_text"](ui.get('sensitive_action_code', 'Security code'))}</label>
                        <input name="confirmation_code" inputmode="numeric" autocomplete="one-time-code" placeholder="{deps["safe_text"](ui.get('sensitive_action_code_placeholder', '6-digit code'))}">
                        <button type="submit" name="action" value="send_security_code" formnovalidate>{deps["safe_text"](ui.get('send_security_code', 'Send security code'))}</button>
                        ''' if deps["user_requires_sensitive_action_2fa"](user) else ''}
                        <button class="danger-button" type="submit" name="action" value="logout_others">{deps["safe_text"](ui.get('sign_out_other_devices', 'Sign out other devices'))}</button>
                    </form>
                </section>
                <section class="card">
                    <h2>{deps["safe_text"](ui.get('recent_session_history', 'Recent session history'))}</h2>
                    {session_rows_html}
                </section>
            </main>
        </body>
        </html>
        """

    @settings_security.route("/settings/<email>/devices/logout_current", methods=["POST"])
    @deps["login_required"]
    def settings_logout_current_device(email):
        deps["validate_csrf_token"]()

        if not deps["user_owns_settings_route"](email):
            abort(403)

        deps["log_security_event"]("current_device_signed_out", email, "User signed out current device from settings")
        session.clear()
        return redirect("/")

    @settings_security.route("/settings/<email>/devices/logout_others", methods=["POST"])
    @deps["login_required"]
    def settings_logout_other_devices(email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            abort(403)

        quoted_email = urllib.parse.quote(user.email, safe="")
        if not deps["verify_user_password"](user, request.form.get("current_password", "")):
            deps["log_security_event"]("other_devices_sign_out_failed", user.email, "current_password_invalid")
            return redirect(f"/settings/{quoted_email}/devices?message=other_devices_password_invalid", code=303)

        action = request.form.get("action", "logout_others")
        if action == "send_security_code":
            if deps["send_sensitive_action_code"](user, "sensitive_logout_others"):
                return redirect(f"/settings/{quoted_email}/devices?message=security_code_sent", code=303)
            deps["log_security_event"]("sensitive_action_code_send_failed", user.email, "purpose=sensitive_logout_others")
            return redirect(f"/settings/{quoted_email}/devices?message=security_code_send_failed", code=303)

        if not deps["verify_sensitive_action_code"](user, "sensitive_logout_others", request.form.get("confirmation_code", "")):
            deps["log_security_event"]("other_devices_sign_out_failed", user.email, "security_code_invalid")
            return redirect(f"/settings/{quoted_email}/devices?message=security_code_invalid", code=303)

        raw_settings = deps["repository_load_user_ai_settings"](user.email)
        current_device_id = deps["current_device_fingerprint"]()
        raw_settings = deps["keep_only_trusted_device"](raw_settings, current_device_id)
        deps["save_user_raw_settings"](user.email, raw_settings)

        deps["rotate_user_session_version"](user.email)
        deps["log_security_event"]("other_devices_signed_out", user.email, "User invalidated other active sessions")
        return redirect(f"/settings/{quoted_email}/devices?message=other_devices_signed_out_success", code=303)

    @settings_security.route("/settings/<email>/trusted_devices", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_trusted_devices(email):
        user = deps["find_user_by_email"](email)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.email):
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        raw_settings = deps["repository_load_user_ai_settings"](user.email)
        devices = raw_settings.get("trusted_devices", []) if isinstance(raw_settings, dict) else []
        current_device = deps["current_device_payload"]()
        current_is_trusted = any(
            device.get("id") == current_device["id"]
            for device in devices
            if isinstance(device, dict)
        )
        current_status = (
            ui.get("trusted_device_yes", "This is a trusted device")
            if current_is_trusted
            else ui.get("new_or_untrusted_device", "New or untrusted device")
        )
        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            action = request.form.get("action", "")
            if action == "trust":
                devices = [device for device in devices if device.get("id") != current_device["id"]]
                devices.append(current_device)
                message = ui.get("trusted_device_added", "Device added to trusted devices.")
            elif action == "remove":
                device_id = deps["clean_text"](request.form.get("device_id", ""))
                devices = [device for device in devices if device.get("id") != device_id]
                message = ui.get("trusted_device_removed", "Device removed from trusted devices.")
            raw_settings["trusted_devices"] = devices
            deps["save_user_raw_settings"](user.email, raw_settings)
            deps["log_security_event"]("trusted_devices_updated", user.email, f"action={action}")

        rows = ""
        for device in devices:
            last_seen = device.get("last_seen_at") or device.get("trusted_at", "")
            rows += f"""
            <article class="row-card">
                <div>
                    <strong>{deps["safe_text"](device.get('label', 'Browser session'))}</strong>
                    <p>{deps["safe_text"](ui.get('ip_address_label', 'IP address'))}: {deps["safe_text"](device.get('ip', ''))}</p>
                    <p>{deps["safe_text"](ui.get('last_seen', 'Last seen'))}: {deps["safe_text"](last_seen or '-')}</p>
                </div>
                <form method="POST">{deps["csrf_input"]()}<input type="hidden" name="action" value="remove"><input type="hidden" name="device_id" value="{deps["safe_text"](device.get('id', ''))}"><button>{deps["safe_text"](ui.get('remove_trust', 'Remove trust'))}</button></form>
            </article>
            """
        if not rows:
            rows = f"<p>{deps['safe_text'](ui.get('no_trusted_devices', 'No trusted devices yet.'))}</p>"

        return f"""
        <!DOCTYPE html><html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{deps["safe_text"](ui.get('trusted_devices_title', 'Trusted devices'))} - AI Match Life</title>
        {deps["settings_control_css"]("820px")}</head>
        <body><main class="page"><a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a><section class="hero"><h1>{deps["safe_text"](ui.get('trusted_devices_title', 'Trusted devices'))}</h1><p>{deps["safe_text"](ui.get('trusted_devices_intro', 'Manage devices you trust for sign-in and account security.'))}</p><p class="message">{deps["safe_text"](message)}</p><div class="muted-card"><strong>{deps["safe_text"](current_status)}</strong><p>{deps["safe_text"](ui.get('ip_address_label', 'IP address'))}: {deps["safe_text"](current_device.get('ip', ''))}</p><p>{deps["safe_text"](ui.get('trusted_device_security_note', 'If you do not recognize a device or IP, remove trust and change your password.'))}</p></div><form method="POST">{deps["csrf_input"]()}<input type="hidden" name="action" value="trust"><button>{deps["safe_text"](ui.get('trust_this_device', 'Trust this device'))}</button></form></section>{rows}</main></body></html>
        """

    @settings_security.route("/settings/<email>/deactivate", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_deactivate_account(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            deps["log_security_event"](
                "account_deactivate_denied",
                deps["current_session_email"](),
                f"target={user.email}",
            )
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        message = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            current_password = request.form.get("current_password", "")

            if not deps["verify_user_password"](user, current_password):
                message = ui.get("current_password_invalid", "Current password is incorrect.")
                deps["log_security_event"]("account_deactivate_failed", user.email, "current_password_invalid")
            else:
                deps["save_user_ai_settings"](user.email, {"account_deactivated": True})
                deps["log_security_event"]("account_deactivated", user.email, "User temporarily deactivated account")
                session.clear()
                return f"""
                <!DOCTYPE html>
                <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>{deps["safe_text"](ui.get('deactivate_account_title', 'Deactivate account'))} - AI Match Life</title>
                    {deps["settings_control_css"]("540px")}
                </head>
                <body>
                    <main class="page">
                        <section class="card">
                            <h1>{deps["safe_text"](ui.get('deactivate_account_title', 'Deactivate account'))}</h1>
                            <p>{deps["safe_text"](ui.get('account_deactivated_success', 'Account deactivated. Sign in again to restore access.'))}</p>
                            <a class="button-link" href="/">{deps["safe_text"](ui.get('login', 'Login'))}</a>
                        </section>
                    </main>
                </body>
                </html>
                """

        return f"""
        <!DOCTYPE html>
        <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{deps["safe_text"](ui.get('deactivate_account_title', 'Deactivate account'))} - AI Match Life</title>
            {deps["settings_control_css"]("620px")}
        </head>
        <body>
            <main class="page">
                <a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
                <section class="hero">
                    <h1>{deps["safe_text"](ui.get('deactivate_account_title', 'Deactivate account'))}</h1>
                    <p>{deps["safe_text"](ui.get('deactivate_account_intro', 'Your account will be hidden from search, AI Matches, and public recommendations. You can restore it the next time you sign in.'))}</p>
                    <p class="warning">{deps["safe_text"](ui.get('deactivate_account_warning', 'This is temporary. Enter your current password to confirm.'))}</p>
                    <p class="message">{deps["safe_text"](message)}</p>
                </section>
                <section class="card">
                    <form method="POST">
                        {deps["csrf_input"]()}
                        <label>{deps["safe_text"](ui.get('current_password', 'Current password'))}</label>
                        <input type="password" name="current_password" autocomplete="current-password" required>
                        <button class="danger-button" type="submit">{deps["safe_text"](ui.get('deactivate_account_confirm', 'Deactivate account'))}</button>
                    </form>
                </section>
            </main>
        </body>
        </html>
        """

    @settings_security.route("/settings/<email>/delete", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_delete_account(email):
        user = deps["find_user_by_email"](email)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.email):
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        message = ""
        message_color = "#facc15"
        contact_type, contact_value = deps["get_user_2fa_contact"](user)

        if request.method == "POST":
            deps["validate_csrf_token"]()
            action = request.form.get("action", "send")
            if action == "send":
                current_password = request.form.get("current_password", "")
                if not deps["verify_user_password"](user, current_password):
                    message = ui.get("current_password_invalid", "Current password is incorrect.")
                else:
                    code = deps["create_verification_code"]("delete_account", contact_type, contact_value)
                    deps["send_verification_code"](contact_type, contact_value, code)
                    session["pending_delete_account"] = user.email
                    message = ui.get("delete_account_code_sent", "Deletion code sent.")
            elif action == "confirm":
                phrase = request.form.get("confirmation_phrase", "")
                code = request.form.get("confirmation_code", "")
                if deps["normalize_email"](session.get("pending_delete_account", "")) != deps["normalize_email"](user.email):
                    message = ui.get("delete_account_code_sent", "Deletion code sent.")
                elif phrase != "DELETE MY ACCOUNT":
                    message = ui.get("delete_account_phrase_invalid", "Confirmation phrase is incorrect.")
                elif not deps["verify_contact_code"]("delete_account", contact_type, contact_value, code):
                    message = ui.get("confirmation_code_invalid", "Confirmation code is invalid or expired.")
                else:
                    deleted_email = user.email
                    snapshot_path = deps["save_account_deletion_snapshot"](deleted_email)
                    deps["log_security_event"]("account_deleted", deleted_email, f"User permanently deleted account; snapshot={snapshot_path}")
                    deps["delete_account_data"](deleted_email)
                    session.clear()
                    return f"""
                    <!DOCTYPE html><html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
                    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{deps["safe_text"](ui.get('delete_account_title', 'Delete account'))} - AI Match Life</title>
                    {deps["settings_control_css"]("520px")}</head>
                    <body><main class="page"><section class="card"><h1>{deps["safe_text"](ui.get('delete_account_title', 'Delete account'))}</h1><p>{deps["safe_text"](ui.get('delete_account_success', 'Account deleted.'))}</p><a class="button-link" href="/">{deps["safe_text"](ui.get('login', 'Login'))}</a></section></main></body></html>
                    """

        return f"""
        <!DOCTYPE html><html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{deps["safe_text"](ui.get('delete_account_title', 'Delete account'))} - AI Match Life</title>
        {deps["settings_control_css"]("720px")}</head>
        <body><main class="page"><a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
            <section class="hero"><h1>{deps["safe_text"](ui.get('delete_account_title', 'Delete account'))}</h1><p>{deps["safe_text"](ui.get('delete_account_intro', 'This deletes your account, posts, messages, notifications, and settings. This cannot be undone.'))}</p><p class="warning">{deps["safe_text"](contact_type)}: {deps["safe_text"](deps["mask_contact_value"](contact_type, contact_value))}</p><p class="message" style="color:{message_color};">{deps["safe_text"](message)}</p></section>
            <section class="card">
                <h2>{deps["safe_text"](ui.get('delete_account_code_sent', 'Deletion code sent.'))}</h2>
                <form method="POST">{deps["csrf_input"]()}<input type="hidden" name="action" value="send"><label>{deps["safe_text"](ui.get('current_password', 'Current password'))}</label><input type="password" name="current_password" autocomplete="current-password" required><button class="danger-button">{deps["safe_text"](ui.get('delete_account_code_sent', 'Deletion code sent.'))}</button></form>
            </section>
            <section class="card"><h2>{deps["safe_text"](ui.get('delete_account_confirm', 'Delete account permanently'))}</h2><form method="POST">{deps["csrf_input"]()}<input type="hidden" name="action" value="confirm"><label>{deps["safe_text"](ui.get('confirmation_code', 'Confirmation code'))}</label><input name="confirmation_code" inputmode="numeric" required><label>{deps["safe_text"](ui.get('delete_account_phrase', 'Type DELETE MY ACCOUNT'))}</label><input name="confirmation_phrase" required><button class="danger-button">{deps["safe_text"](ui.get('delete_account_confirm', 'Delete account permanently'))}</button></form></section>
        </main></body></html>
        """

    @settings_security.route("/settings/<email>/people_controls")
    @deps["login_required"]
    def settings_people_controls(email):
        user = deps["find_user_by_email"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            deps["log_security_event"](
                "people_controls_denied",
                deps["current_session_email"](),
                f"target={user.email}",
            )
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        user_email = deps["normalize_email"](user.email)
        blocks_data = deps["load_blocks"]()
        restrictions_data = deps["load_restrictions"]()
        hidden_stories_data = deps["load_hidden_stories"]()

        blocked_users = deps["users_from_email_list"](blocks_data.get("blocks", {}).get(user_email, []))
        restricted_users = deps["users_from_email_list"](restrictions_data.get("restrictions", {}).get(user_email, []))
        hidden_story_users = deps["users_from_email_list"](hidden_stories_data.get("hidden_stories", {}).get(user_email, []))

        def render_people_section(title, people, action_path, action_label):
            cards = ""
            for person in people:
                cards += f"""
                <article class="person-row">
                    <div class="person-main">
                        <img src="{deps["get_avatar_url"](person.email)}" alt="Avatar">
                        <div>
                            <strong>{deps["safe_text"](person.name)}</strong>
                            <p>{deps["safe_text"](person.email)}</p>
                        </div>
                    </div>
                    <a class="person-action" href="{action_path(person)}">{deps["safe_text"](action_label)}</a>
                </article>
                """

            if cards == "":
                cards = f'<div class="empty-state">{deps["safe_text"](ui.get("people_controls_empty", "No saved restrictions yet."))}</div>'

            return f"""
            <section class="panel">
                <h2>{deps["safe_text"](title)}</h2>
                {cards}
            </section>
            """

        blocked_html = render_people_section(
            ui.get("blocked_users", "Blocked users"),
            blocked_users,
            lambda person: f"/settings/{deps['safe_text'](user.email)}/people_controls/unblock/{deps['safe_text'](person.email)}",
            ui.get("unblock", "Unblock"),
        )
        restricted_html = render_people_section(
            ui.get("restricted_users", "Restricted users"),
            restricted_users,
            lambda person: f"/settings/{deps['safe_text'](user.email)}/people_controls/unrestrict/{deps['safe_text'](person.email)}",
            ui.get("unrestrict", "Remove restriction"),
        )
        hidden_stories_html = render_people_section(
            ui.get("hidden_stories", "Hidden Stories"),
            hidden_story_users,
            lambda person: f"/settings/{deps['safe_text'](user.email)}/people_controls/show_stories/{deps['safe_text'](person.email)}",
            ui.get("show_stories_again", "Show Stories"),
        )

        return f"""
        <!DOCTYPE html>
        <html lang="{deps["safe_text"](ui.get('language_code', 'ru'))}" dir="{deps["safe_text"](ui.get('text_direction', 'ltr'))}">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{deps["safe_text"](ui.get('people_controls_title', 'People controls'))} - AI Match Life</title>
            <style>
                *{{box-sizing:border-box}}
                body{{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;padding:28px;}}
                .page{{max-width:980px;margin:auto;}}
                .back{{display:inline-flex;background:#111827;border:1px solid rgba(148,163,184,0.14);color:white;text-decoration:none;border-radius:8px;padding:11px 14px;font-weight:900;margin-bottom:18px;}}
                .hero,.panel,.person-row,.empty-state{{background:#1e293b;border:1px solid rgba(148,163,184,0.14);border-radius:8px;padding:20px;margin-bottom:14px;}}
                .hero h1{{margin:0 0 8px 0;font-size:30px;}}
                .hero p,.person-main p{{margin:0;color:#cbd5e1;line-height:1.45;}}
                .panel h2{{margin:0 0 14px 0;}}
                .person-row{{display:flex;align-items:center;justify-content:space-between;gap:14px;background:#111827;}}
                .person-main{{display:flex;align-items:center;gap:12px;min-width:0;}}
                .person-main img{{width:46px;height:46px;border-radius:50%;object-fit:cover;background:#334155;}}
                .person-action{{background:#2563eb;color:white;text-decoration:none;border-radius:8px;padding:10px 13px;font-weight:900;white-space:nowrap;}}
                @media(max-width:680px){{body{{padding:18px}}.person-row{{align-items:flex-start;flex-direction:column}}.person-action{{width:100%;text-align:center}}}}
            </style>
        </head>
        <body>
            <main class="page">
                <a class="back" href="/settings/{deps["safe_text"](user.email)}">{deps["safe_text"](ui.get('back', 'Back'))}</a>
                <section class="hero">
                    <h1>{deps["safe_text"](ui.get('people_controls_title', 'People controls'))}</h1>
                    <p>{deps["safe_text"](ui.get('people_controls_intro', 'Manage blocked users, restrictions, and hidden Stories.'))}</p>
                </section>
                {blocked_html}
                {restricted_html}
                {hidden_stories_html}
            </main>
        </body>
        </html>
        """

    @settings_security.route("/settings/<email>/people_controls/unblock/<target_email>")
    @deps["login_required"]
    def settings_unblock_user(email, target_email):
        if not deps["user_owns_settings_route"](email):
            abort(403)

        deps["unblock_user_account"](deps["normalize_email"](email), deps["normalize_email"](target_email))
        deps["log_security_event"]("settings_user_unblocked", email, f"Unblocked {target_email}")
        return redirect(f"/settings/{deps['safe_text'](email)}/people_controls")

    @settings_security.route("/settings/<email>/people_controls/unrestrict/<target_email>")
    @deps["login_required"]
    def settings_unrestrict_user(email, target_email):
        if not deps["user_owns_settings_route"](email):
            abort(403)

        deps["unrestrict_user_account"](deps["normalize_email"](email), deps["normalize_email"](target_email))
        deps["log_security_event"]("settings_user_unrestricted", email, f"Unrestricted {target_email}")
        return redirect(f"/settings/{deps['safe_text'](email)}/people_controls")

    @settings_security.route("/settings/<email>/people_controls/show_stories/<target_email>")
    @deps["login_required"]
    def settings_show_stories_user(email, target_email):
        if not deps["user_owns_settings_route"](email):
            abort(403)

        deps["show_stories_from_user"](deps["normalize_email"](email), deps["normalize_email"](target_email))
        deps["log_security_event"]("settings_stories_shown", email, f"Stories shown from {target_email}")
        return redirect(f"/settings/{deps['safe_text'](email)}/people_controls")

    return settings_security
