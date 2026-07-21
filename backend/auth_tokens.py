import base64
import hashlib
import hmac
import json
import time
import secrets


DEFAULT_ACCESS_TOKEN_SECONDS = 60 * 60 * 24 * 7
DEFAULT_REFRESH_TOKEN_SECONDS = 60 * 60 * 24 * 30


def _base64url_encode(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def normalize_email(value):
    return str(value or "").strip().lower()


def sign_payload(payload, secret):
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(str(secret).encode("utf-8"), payload_json, hashlib.sha256).digest()
    return f"{_base64url_encode(payload_json)}.{_base64url_encode(signature)}"


def verify_signed_payload(token, secret):
    try:
        payload_part, signature_part = str(token or "").split(".", 1)
        payload_json = _base64url_decode(payload_part)
        provided_signature = _base64url_decode(signature_part)
    except Exception:
        return None

    expected_signature = hmac.new(str(secret).encode("utf-8"), payload_json, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None

    try:
        payload = json.loads(payload_json.decode("utf-8"))
    except Exception:
        return None

    return payload if isinstance(payload, dict) else None


def create_access_token(email, secret, expires_in_seconds=DEFAULT_ACCESS_TOKEN_SECONDS, issued_at=None, session_version=1):
    issued_at = int(issued_at if issued_at is not None else time.time())
    expires_in_seconds = int(expires_in_seconds or DEFAULT_ACCESS_TOKEN_SECONDS)
    payload = {
        "type": "access",
        "email": normalize_email(email),
        "iat": issued_at,
        "exp": issued_at + max(expires_in_seconds, 1),
        "session_version": max(int(session_version or 1), 1),
    }
    return sign_payload(payload, secret)


def verify_access_token(token, secret, now=None):
    payload = verify_signed_payload(token, secret)
    if not payload or payload.get("type") != "access":
        return None

    now = int(now if now is not None else time.time())
    try:
        expires_at = int(payload.get("exp", 0))
        session_version = max(int(payload.get("session_version", 1)), 1)
    except (TypeError, ValueError):
        return None

    email = normalize_email(payload.get("email"))
    if not email or expires_at < now:
        return None

    return {
        "email": email,
        "issued_at": int(payload.get("iat", 0) or 0),
        "expires_at": expires_at,
        "session_version": session_version,
    }


def create_refresh_token(email, secret, session_version=1, expires_in_seconds=DEFAULT_REFRESH_TOKEN_SECONDS,
                         issued_at=None, token_id=None, family_id=None):
    issued_at = int(issued_at if issued_at is not None else time.time())
    token_id = str(token_id or secrets.token_urlsafe(24))
    family_id = str(family_id or secrets.token_urlsafe(24))
    payload = {
        "type": "refresh",
        "email": normalize_email(email),
        "jti": token_id,
        "family_id": family_id,
        "session_version": max(int(session_version or 1), 1),
        "iat": issued_at,
        "exp": issued_at + max(int(expires_in_seconds or DEFAULT_REFRESH_TOKEN_SECONDS), 1),
    }
    return sign_payload(payload, secret)


def verify_refresh_token(token, secret, now=None):
    payload = verify_signed_payload(token, secret)
    if not payload or payload.get("type") != "refresh":
        return None
    now = int(now if now is not None else time.time())
    try:
        expires_at = int(payload.get("exp", 0))
        session_version = max(int(payload.get("session_version", 1)), 1)
    except (TypeError, ValueError):
        return None
    email = normalize_email(payload.get("email"))
    token_id = str(payload.get("jti") or "").strip()
    family_id = str(payload.get("family_id") or "").strip()
    if not email or not token_id or not family_id or expires_at < now:
        return None
    return {
        "email": email,
        "token_id": token_id,
        "family_id": family_id,
        "session_version": session_version,
        "issued_at": int(payload.get("iat", 0) or 0),
        "expires_at": expires_at,
    }


def hash_token(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
