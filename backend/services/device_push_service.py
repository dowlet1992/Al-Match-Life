import hashlib
import re


SUPPORTED_PLATFORMS = {"android", "ios", "web"}
DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
TOKEN_PATTERN = re.compile(r"^[\x21-\x7e]{32,4096}$")


def normalize_registration(data, clean_text=lambda value: str(value or "").strip()):
    data = data if isinstance(data, dict) else {}
    platform = clean_text(data.get("platform", "")).lower()
    device_id = clean_text(data.get("device_id", ""))
    token = str(data.get("token", "") or "").strip()
    if platform not in SUPPORTED_PLATFORMS:
        return None, "Unsupported push platform"
    if not DEVICE_ID_PATTERN.fullmatch(device_id):
        return None, "Invalid device identifier"
    if not TOKEN_PATTERN.fullmatch(token):
        return None, "Invalid push token"
    return {
        "platform": platform,
        "device_id": device_id,
        "token": token,
        "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "app_version": clean_text(data.get("app_version", ""))[:64],
        "locale": clean_text(data.get("locale", ""))[:35].lower(),
    }, None


def public_device(item):
    return {
        "device_id": str(item.get("device_id", "")),
        "platform": str(item.get("platform", "")),
        "app_version": str(item.get("app_version", "")),
        "locale": str(item.get("locale", "")),
        "last_seen_at": str(item.get("last_seen_at", "")),
    }
