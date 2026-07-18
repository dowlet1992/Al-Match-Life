from backend.services.security_activity_service import security_event_display


def test_security_event_display_maps_known_event_to_user_text():
    ui = {
        "security_event_login_success": "Signed in",
        "security_category_login": "Login",
        "security_detail_2fa_not_required": "Signed in without an extra code.",
    }

    display = security_event_display({
        "event": "login_success",
        "details": "2FA not required",
        "time": "2026-07-17 10:00:00",
        "ip": "127.0.0.1",
    }, ui)

    assert display == {
        "title": "Signed in",
        "category": "Login",
        "tone": "good",
        "details": "Signed in without an extra code.",
        "time": "2026-07-17 10:00:00",
        "ip": "127.0.0.1",
    }


def test_security_event_display_handles_unknown_event():
    display = security_event_display({"event": "custom_event"}, {})

    assert display["title"] == "custom_event"
    assert display["category"] == "System"
    assert display["tone"] == "info"
