import secrets
import time

from backend.auth_tokens import (
    DEFAULT_REFRESH_TOKEN_SECONDS,
    create_refresh_token,
    hash_token,
    verify_refresh_token,
)


def _session_record(payload, token, device_id):
    return {
        "token_id": payload["token_id"],
        "family_id": payload["family_id"],
        "email": payload["email"],
        "token_hash": hash_token(token),
        "device_id": str(device_id or "")[:160],
        "session_version": payload["session_version"],
        "issued_at": payload["issued_at"],
        "expires_at": payload["expires_at"],
    }


def issue_refresh_token(email, secret, session_version, repository, device_id="",
                        expires_in_seconds=DEFAULT_REFRESH_TOKEN_SECONDS, now=None, family_id=None):
    issued_at = int(now if now is not None else time.time())
    token_id = secrets.token_urlsafe(24)
    family_id = str(family_id or secrets.token_urlsafe(24))
    token = create_refresh_token(
        email, secret, session_version=session_version,
        expires_in_seconds=expires_in_seconds, issued_at=issued_at,
        token_id=token_id, family_id=family_id,
    )
    payload = verify_refresh_token(token, secret, now=issued_at)
    repository.create(_session_record(payload, token, device_id))
    return {
        "refresh_token": token,
        "refresh_expires_in": int(expires_in_seconds),
        "family_id": family_id,
    }


def rotate_refresh_token(raw_token, secret, current_session_version, repository, device_id="",
                         expires_in_seconds=DEFAULT_REFRESH_TOKEN_SECONDS, now=None):
    now = int(now if now is not None else time.time())
    payload = verify_refresh_token(raw_token, secret, now=now)
    if not payload:
        return {"ok": False, "error": "invalid_refresh_token"}

    stored = repository.get(payload["token_id"])
    if not stored:
        return {"ok": False, "error": "invalid_refresh_token"}
    if stored.get("email") != payload["email"] or stored.get("family_id") != payload["family_id"]:
        repository.revoke_family(payload["family_id"])
        return {"ok": False, "error": "refresh_token_reuse"}
    if int(payload["session_version"]) != int(current_session_version):
        repository.revoke_family(payload["family_id"])
        return {"ok": False, "error": "refresh_token_revoked"}

    replacement_id = secrets.token_urlsafe(24)
    replacement = create_refresh_token(
        payload["email"], secret, session_version=current_session_version,
        expires_in_seconds=expires_in_seconds, issued_at=now,
        token_id=replacement_id, family_id=payload["family_id"],
    )
    replacement_payload = verify_refresh_token(replacement, secret, now=now)
    replacement_record = _session_record(replacement_payload, replacement, device_id or stored.get("device_id", ""))
    rotation_status = repository.rotate(payload["token_id"], hash_token(raw_token), replacement_record)
    if rotation_status == "reuse":
        return {"ok": False, "error": "refresh_token_reuse"}
    if rotation_status != "rotated":
        return {"ok": False, "error": "invalid_refresh_token"}
    return {
        "ok": True,
        "email": payload["email"],
        "refresh_token": replacement,
        "refresh_expires_in": int(expires_in_seconds),
        "family_id": payload["family_id"],
    }


def revoke_refresh_token(raw_token, secret, repository):
    payload = verify_refresh_token(raw_token, secret)
    if not payload:
        return False
    stored = repository.get(payload["token_id"])
    if not stored or stored.get("family_id") != payload["family_id"]:
        return False
    return repository.revoke_family(payload["family_id"])
