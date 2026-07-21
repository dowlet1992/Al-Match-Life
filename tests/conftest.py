import pytest


@pytest.fixture(autouse=True)
def isolate_runtime_security_log(monkeypatch):
    """Prevent test requests from writing audit/settings state into live runtime data."""
    try:
        import app
    except ImportError:
        return

    monkeypatch.setattr(app, "log_security_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "issue_mobile_refresh_token",
        lambda user: {"refresh_token": "test-refresh-token", "refresh_expires_in": 3600},
    )
    monkeypatch.setattr(
        app,
        "rotate_mobile_refresh_token",
        lambda token: {"ok": False, "error": "invalid_refresh_token"},
    )
    monkeypatch.setattr(app, "revoke_mobile_refresh_token", lambda token: False)
    monkeypatch.setattr(app, "purge_call_caption_data", lambda room_id: False)
    monkeypatch.setattr(app, "delete_call_rooms_for_participant", lambda email: 0)
    monkeypatch.setattr(app, "revoke_all_push_devices", lambda email: 0)
    monkeypatch.setattr(app, "prune_expired_call_rooms", lambda **options: 0)
    monkeypatch.setattr(app, "append_call_quality_sample", lambda *args, **options: "inactive")
    monkeypatch.setattr(app, "acknowledge_call_signals", lambda *args, **options: ("missing", 0))
    monkeypatch.setattr(app, "expire_call_signal_room", lambda *args, **options: None)
    monkeypatch.setattr(app, "expire_due_call_rooms", lambda *args, **options: [])
    monkeypatch.setattr(
        app,
        "call_signal_poll_limiter",
        app.call_signal_security_service.PollRateLimiter(),
    )
    settings_by_email = {}
    monkeypatch.setattr(
        app,
        "repository_load_user_ai_settings",
        lambda email: dict(settings_by_email.get(str(email or "").strip().lower(), {})),
    )
    monkeypatch.setattr(
        app,
        "repository_save_user_ai_settings",
        lambda email, settings: settings_by_email.__setitem__(
            str(email or "").strip().lower(),
            dict(settings) if isinstance(settings, dict) else {},
        ),
    )
