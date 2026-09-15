import json
import urllib.parse
from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, session


def create_settings_security_blueprint(deps):
    settings_security = Blueprint("settings_security", __name__)

    @settings_security.route("/settings/<email>/security_activity")
    @deps["login_required"]
    def settings_security_activity(email):
        user = deps["find_user_by_identifier"](email)

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
        event_views = [
            deps["security_event_display"](event, ui)
            for event in events
        ]
        return render_template(
            "settings_security_activity.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            events=event_views,
        )

    @settings_security.route("/settings/<email>/data_export")
    @deps["login_required"]
    def settings_data_export(email):
        user = deps["find_user_by_identifier"](email)

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
        response.headers["Content-Disposition"] = f'attachment; filename="novix-{normalized_email}-export.json"'
        return response

    @settings_security.route("/settings/<email>/password", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_change_password(email):
        user = deps["find_user_by_identifier"](email)

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
                deps["rotate_user_session_version"](user.email)
                deps["log_security_event"]("password_changed", user.email, "User changed password from settings")
                message = ui.get("password_changed_success", "Password changed successfully.")
                message_color = "#22c55e"

        return render_template(
            "settings_password.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            message=message,
            message_is_success=message_color == "#22c55e",
            requires_security_code=requires_security_code,
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/email_phone", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_email_phone(email):
        user = deps["find_user_by_identifier"](email)
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

        pending_view = {
            "type": pending.get("type", ""),
            "value": pending.get("value", ""),
        } if pending else None
        return render_template(
            "settings_email_phone.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            message=message,
            message_is_success=message_color == "#22c55e",
            pending=pending_view,
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/devices")
    @deps["login_required"]
    def settings_devices(email):
        user = deps["find_user_by_identifier"](email)

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
        device_label = user_agent[:140] if user_agent else ui.get("browser_session", "Browser session")
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
        session_views = [
            {
                "event": event.get("event", ""),
                "details": event.get("details", ""),
                "time": event.get("time", ""),
                "ip": event.get("ip", ""),
            }
            for event in session_events
        ]
        return render_template(
            "settings_devices.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            message=message,
            login_time=login_time or "-",
            ip_address=ip_address,
            device_label=device_label,
            trust_status=trust_status,
            session_events=session_views,
            requires_security_code=deps["user_requires_sensitive_action_2fa"](user),
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/devices/logout_current", methods=["POST"])
    @deps["login_required"]
    def settings_logout_current_device(email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](email)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            abort(403)

        deps["log_security_event"]("current_device_signed_out", user.email, "User signed out current device from settings")
        session.clear()
        return redirect("/")

    @settings_security.route("/settings/<email>/devices/logout_others", methods=["POST"])
    @deps["login_required"]
    def settings_logout_other_devices(email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](email)

        if user is None:
            return "User not found", 404

        if not deps["user_owns_settings_route"](user.email):
            abort(403)

        settings_identifier = user.id
        if not deps["verify_user_password"](user, request.form.get("current_password", "")):
            deps["log_security_event"]("other_devices_sign_out_failed", user.email, "current_password_invalid")
            return redirect(f"/settings/{settings_identifier}/devices?message=other_devices_password_invalid", code=303)

        action = request.form.get("action", "logout_others")
        if action == "send_security_code":
            if deps["send_sensitive_action_code"](user, "sensitive_logout_others"):
                return redirect(f"/settings/{settings_identifier}/devices?message=security_code_sent", code=303)
            deps["log_security_event"]("sensitive_action_code_send_failed", user.email, "purpose=sensitive_logout_others")
            return redirect(f"/settings/{settings_identifier}/devices?message=security_code_send_failed", code=303)

        if not deps["verify_sensitive_action_code"](user, "sensitive_logout_others", request.form.get("confirmation_code", "")):
            deps["log_security_event"]("other_devices_sign_out_failed", user.email, "security_code_invalid")
            return redirect(f"/settings/{settings_identifier}/devices?message=security_code_invalid", code=303)

        raw_settings = deps["repository_load_user_ai_settings"](user.email)
        current_device_id = deps["current_device_fingerprint"]()
        raw_settings = deps["keep_only_trusted_device"](raw_settings, current_device_id)
        deps["save_user_raw_settings"](user.email, raw_settings)

        deps["rotate_user_session_version"](user.email)
        deps["log_security_event"]("other_devices_signed_out", user.email, "User invalidated other active sessions")
        return redirect(f"/settings/{settings_identifier}/devices?message=other_devices_signed_out_success", code=303)

    @settings_security.route("/settings/<email>/trusted_devices", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_trusted_devices(email):
        user = deps["find_user_by_identifier"](email)
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

        device_views = [
            {
                "id": device.get("id", ""),
                "label": device.get("label") or ui.get("browser_session", "Browser session"),
                "ip": device.get("ip", ""),
                "last_seen": device.get("last_seen_at") or device.get("trusted_at", "") or "-",
            }
            for device in devices
            if isinstance(device, dict)
        ]
        return render_template(
            "settings_trusted_devices.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            message=message,
            current_status=current_status,
            current_device_ip=current_device.get("ip", ""),
            devices=device_views,
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/deactivate", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_deactivate_account(email):
        user = deps["find_user_by_identifier"](email)

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
                deps["rotate_user_session_version"](user.email)
                deps["log_security_event"]("account_deactivated", user.email, "User temporarily deactivated account")
                session.clear()
                return render_template(
                    "account_action_success.html",
                    ui=ui,
                    title=ui.get("deactivate_account_title", "Deactivate account"),
                    message=ui.get("account_deactivated_success", "Account deactivated. Sign in again to restore access."),
                )

        return render_template(
            "settings_deactivate_account.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            message=message,
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/delete", methods=["GET", "POST"])
    @deps["login_required"]
    def settings_delete_account(email):
        user = deps["find_user_by_identifier"](email)
        if user is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.email):
            abort(403)

        ui = deps["translation_bundle"](deps["get_current_language"](user))
        message = ""
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
                    return render_template(
                        "account_action_success.html",
                        ui=ui,
                        title=ui.get("delete_account_title", "Delete account"),
                        message=ui.get("delete_account_success", "Account deleted."),
                    )

        return render_template(
            "settings_delete_account.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            message=message,
            contact_type=contact_type,
            masked_contact=deps["mask_contact_value"](contact_type, contact_value),
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/people_controls")
    @deps["login_required"]
    def settings_people_controls(email):
        user = deps["find_user_by_identifier"](email)

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

        def people_view(people, action):
            return [
                {
                    "name": person.name,
                    "email": person.email,
                    "avatar_url": deps["get_avatar_url"](person.email),
                    "action_url": (
                        f"/settings/{user.id}/people_controls/{action}/{person.id}"
                    ),
                }
                for person in people
            ]

        sections = [
            {
                "title": ui.get("blocked_users", "Blocked users"),
                "action_label": ui.get("unblock", "Unblock"),
                "people": people_view(blocked_users, "unblock"),
            },
            {
                "title": ui.get("restricted_users", "Restricted users"),
                "action_label": ui.get("unrestrict", "Remove restriction"),
                "people": people_view(restricted_users, "unrestrict"),
            },
            {
                "title": ui.get("hidden_stories", "Hidden Stories"),
                "action_label": ui.get("show_stories_again", "Show Stories"),
                "people": people_view(hidden_story_users, "show_stories"),
            },
        ]

        return render_template(
            "settings_people_controls.html",
            ui=ui,
            email=user.email,
            user_id=user.id,
            sections=sections,
            csrf_token_input=deps["csrf_input"](),
        )

    @settings_security.route("/settings/<email>/people_controls/unblock/<target_email>", methods=["POST"])
    @deps["login_required"]
    def settings_unblock_user(email, target_email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](email)
        target = deps["find_user_by_identifier"](target_email)
        if user is None or target is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            abort(403)

        deps["unblock_user_account"](deps["normalize_email"](user.email), deps["normalize_email"](target.email))
        deps["log_security_event"]("settings_user_unblocked", user.email, f"Unblocked {target.email}")
        return redirect(f"/settings/{user.id}/people_controls")

    @settings_security.route("/settings/<email>/people_controls/unrestrict/<target_email>", methods=["POST"])
    @deps["login_required"]
    def settings_unrestrict_user(email, target_email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](email)
        target = deps["find_user_by_identifier"](target_email)
        if user is None or target is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            abort(403)

        deps["unrestrict_user_account"](deps["normalize_email"](user.email), deps["normalize_email"](target.email))
        deps["log_security_event"]("settings_user_unrestricted", user.email, f"Unrestricted {target.email}")
        return redirect(f"/settings/{user.id}/people_controls")

    @settings_security.route("/settings/<email>/people_controls/show_stories/<target_email>", methods=["POST"])
    @deps["login_required"]
    def settings_show_stories_user(email, target_email):
        deps["validate_csrf_token"]()
        user = deps["find_user_by_identifier"](email)
        target = deps["find_user_by_identifier"](target_email)
        if user is None or target is None:
            return "User not found", 404
        if not deps["user_owns_settings_route"](user.id):
            abort(403)

        deps["show_stories_from_user"](deps["normalize_email"](user.email), deps["normalize_email"](target.email))
        deps["log_security_event"]("settings_stories_shown", user.email, f"Stories shown from {target.email}")
        return redirect(f"/settings/{user.id}/people_controls")

    return settings_security
