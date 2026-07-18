from backend.services import device_security_service


def test_session_version_helpers_normalize_and_rotate_versions():
    assert device_security_service.session_version_from_settings({}) == 1
    assert device_security_service.session_version_from_settings({"session_version": "3"}) == 3
    assert device_security_service.session_version_from_settings({"session_version": "bad"}) == 1

    settings, version = device_security_service.rotate_session_version(
        {"session_version": 2},
        "2026-07-17 10:00:00",
    )

    assert version == 3
    assert settings["session_version"] == 3
    assert settings["session_version_changed_at"] == "2026-07-17 10:00:00"
    assert device_security_service.is_session_version_current("3", 3) is True
    assert device_security_service.is_session_version_current("2", 3) is False
    assert device_security_service.is_session_version_current(None, 3) is True


def test_update_trusted_device_seen_updates_existing_device_only():
    settings = {
        "trusted_devices": [
            {
                "id": "device-1",
                "label": "Old browser",
                "ip": "old-ip",
                "trusted_at": "2026-07-16 10:00:00",
                "last_seen_at": "2026-07-16 10:00:00",
            }
        ]
    }

    updated_settings, updated = device_security_service.update_trusted_device_seen(settings, {
        "id": "device-1",
        "label": "Fresh browser",
        "ip": "203.0.113.7",
        "trusted_at": "2026-07-17 10:00:00",
        "last_seen_at": "2026-07-17 10:05:00",
    })

    assert updated is True
    assert updated_settings["trusted_devices"][0]["label"] == "Fresh browser"
    assert updated_settings["trusted_devices"][0]["ip"] == "203.0.113.7"
    assert updated_settings["trusted_devices"][0]["trusted_at"] == "2026-07-16 10:00:00"
    assert updated_settings["trusted_devices"][0]["last_seen_at"] == "2026-07-17 10:05:00"

    unchanged_settings, updated = device_security_service.update_trusted_device_seen(settings, {"id": "missing"})
    assert updated is False
    assert unchanged_settings == settings


def test_device_trust_and_keep_only_current_device():
    settings = {
        "trusted_devices": [
            {"id": "current-device", "label": "Current"},
            {"id": "old-device", "label": "Old"},
        ]
    }

    assert device_security_service.is_device_trusted(settings, "current-device") is True
    assert device_security_service.is_device_trusted(settings, "missing-device") is False

    filtered = device_security_service.keep_only_trusted_device(settings, "current-device")
    assert filtered["trusted_devices"] == [{"id": "current-device", "label": "Current"}]
