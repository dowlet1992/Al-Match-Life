import json
import secrets
import time

import jwt


MAX_PARTICIPANTS = 4
TOKEN_TTL_SECONDS = 15 * 60


def new_room_id():
    return f"novix_{secrets.token_urlsafe(18)}"


def normalize_participants(owner_email, requested, normalize_email):
    participants = [normalize_email(owner_email)]
    for value in requested if isinstance(requested, list) else []:
        email = normalize_email(value)
        if email and email not in participants:
            participants.append(email)
    return participants[:MAX_PARTICIPANTS]


def issue_access_token(api_key, api_secret, room_id, identity, display_name, metadata=None, now=None):
    now = int(now if now is not None else time.time())
    if not api_key or len(str(api_secret or "")) < 16:
        return ""
    payload = {
        "iss": str(api_key),
        "sub": str(identity),
        "nbf": now - 5,
        "exp": now + TOKEN_TTL_SECONDS,
        "name": str(display_name or "NOVIX user")[:120],
        "metadata": json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
        "video": {
            "roomJoin": True,
            "room": str(room_id),
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
        },
    }
    return jwt.encode(payload, str(api_secret), algorithm="HS256")


def room_participants(room, normalize_email):
    if not isinstance(room, dict):
        return []
    values = room.get("participants", [])
    return [normalize_email(value) for value in values if normalize_email(value)] if isinstance(values, list) else []


def room_owner(room, normalize_email):
    if not isinstance(room, dict):
        return ""
    messages = room.get("messages", [])
    for message in messages if isinstance(messages, list) else []:
        if isinstance(message, dict) and message.get("type") == "conference_invite":
            payload = message.get("payload", {}) if isinstance(message.get("payload"), dict) else {}
            return normalize_email(payload.get("owner") or message.get("from"))
    return ""


def room_call_type(room):
    if not isinstance(room, dict):
        return "video"
    for message in room.get("messages", []) if isinstance(room.get("messages"), list) else []:
        if isinstance(message, dict) and message.get("type") == "conference_invite":
            payload = message.get("payload", {}) if isinstance(message.get("payload"), dict) else {}
            return "audio" if payload.get("call_type") == "audio" else "video"
    return "video"
