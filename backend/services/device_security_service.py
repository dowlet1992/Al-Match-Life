def session_version_from_settings(settings):
    settings = settings if isinstance(settings, dict) else {}
    try:
        return max(1, int(settings.get("session_version", 1)))
    except (TypeError, ValueError):
        return 1


def rotate_session_version(settings, changed_at):
    settings = dict(settings) if isinstance(settings, dict) else {}
    new_version = session_version_from_settings(settings) + 1
    settings["session_version"] = new_version
    settings["session_version_changed_at"] = changed_at
    return settings, new_version


def is_session_version_current(session_version, current_version):
    if session_version is None:
        return True

    try:
        return int(session_version) == int(current_version)
    except (TypeError, ValueError):
        return False


def update_trusted_device_seen(settings, current_device):
    settings = dict(settings) if isinstance(settings, dict) else {}
    devices = settings.get("trusted_devices", [])
    if not isinstance(devices, list):
        return settings, False

    current_device = current_device if isinstance(current_device, dict) else {}
    current_device_id = current_device.get("id")
    if not current_device_id:
        return settings, False

    updated = False
    for device in devices:
        if not isinstance(device, dict):
            continue
        if device.get("id") == current_device_id:
            device["label"] = current_device.get("label", device.get("label", "Browser session"))
            device["ip"] = current_device.get("ip", device.get("ip", "unknown"))
            device["last_seen_at"] = current_device.get("last_seen_at", device.get("last_seen_at", ""))
            device.setdefault("trusted_at", current_device.get("trusted_at", ""))
            updated = True
            break

    if updated:
        settings["trusted_devices"] = devices

    return settings, updated


def is_device_trusted(settings, current_device_id):
    settings = settings if isinstance(settings, dict) else {}
    devices = settings.get("trusted_devices", [])
    if not isinstance(devices, list) or not current_device_id:
        return False

    return any(
        isinstance(device, dict) and device.get("id") == current_device_id
        for device in devices
    )


def keep_only_trusted_device(settings, current_device_id):
    settings = dict(settings) if isinstance(settings, dict) else {}
    trusted_devices = settings.get("trusted_devices", [])
    if isinstance(trusted_devices, list):
        settings["trusted_devices"] = [
            device for device in trusted_devices
            if isinstance(device, dict) and device.get("id") == current_device_id
        ]
    return settings
