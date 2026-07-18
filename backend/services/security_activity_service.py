SECURITY_EVENT_UI = {
    "login_success": ("security_event_login_success", "security_category_login", "good"),
    "api_login_success": ("security_event_login_success", "security_category_login", "good"),
    "login_2fa_success": ("security_event_login_2fa_success", "security_category_login", "good"),
    "login_2fa_required": ("security_event_login_2fa_required", "security_category_login", "info"),
    "login_failed": ("security_event_login_failed", "security_category_login", "warning"),
    "login_locked": ("security_event_login_locked", "security_category_login", "danger"),
    "login_unverified_account": ("security_event_unverified_login", "security_category_login", "warning"),
    "password_changed": ("security_event_password_changed", "security_category_account", "good"),
    "password_change_failed": ("security_event_password_change_failed", "security_category_account", "warning"),
    "contact_changed": ("security_event_contact_changed", "security_category_account", "good"),
    "trusted_devices_updated": ("security_event_trusted_devices_updated", "security_category_devices", "info"),
    "current_device_signed_out": ("security_event_current_device_signed_out", "security_category_devices", "info"),
    "other_devices_signed_out": ("security_event_other_devices_signed_out", "security_category_devices", "good"),
    "other_devices_sign_out_failed": ("security_event_other_devices_failed", "security_category_devices", "warning"),
    "stale_session_rejected": ("security_event_stale_session_rejected", "security_category_devices", "danger"),
    "stale_api_session_rejected": ("security_event_stale_session_rejected", "security_category_devices", "danger"),
    "sensitive_action_code_sent": ("security_event_code_sent", "security_category_verification", "info"),
    "sensitive_action_code_send_failed": ("security_event_code_send_failed", "security_category_verification", "warning"),
    "verification_code_failed": ("security_event_code_failed", "security_category_verification", "warning"),
    "verification_attempts_locked": ("security_event_code_locked", "security_category_verification", "danger"),
    "account_verified": ("security_event_account_verified", "security_category_account", "good"),
    "account_reactivated": ("security_event_account_reactivated", "security_category_account", "good"),
    "account_deactivated": ("security_event_account_deactivated", "security_category_account", "warning"),
    "account_deleted": ("security_event_account_deleted", "security_category_account", "danger"),
}


def clean_text(value):
    return str(value or "").strip()


def security_event_display(event, ui):
    event = event if isinstance(event, dict) else {}
    ui = ui if isinstance(ui, dict) else {}
    event_type = clean_text(event.get("event", ""))
    label_key, category_key, tone = SECURITY_EVENT_UI.get(
        event_type,
        ("security_event_unknown", "security_category_system", "info"),
    )
    details = clean_text(event.get("details", ""))
    if details.startswith("purpose="):
        details = ui.get("security_detail_verification_code", "Verification code action.")
    elif details == "2FA not required":
        details = ui.get("security_detail_2fa_not_required", "Signed in without an extra code.")
    elif details == "current_password_invalid":
        details = ui.get("security_detail_current_password_invalid", "Current password was incorrect.")
    elif details == "security_code_invalid":
        details = ui.get("security_detail_security_code_invalid", "Security code was incorrect or expired.")

    return {
        "title": ui.get(label_key, event_type or ui.get("security_event_unknown", "Security event")),
        "category": ui.get(category_key, ui.get("security_category_system", "System")),
        "tone": tone,
        "details": details,
        "time": clean_text(event.get("time", "")),
        "ip": clean_text(event.get("ip", "")),
    }
