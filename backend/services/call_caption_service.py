import time


MAX_CAPTION_LENGTH = 1000
MAX_ROOM_CAPTIONS = 120
CAPTION_TTL_SECONDS = 60 * 60 * 6
TEMPORARY_CAPTION_KEYS = ("captions", "transcription_reservations", "quality_samples")


def clean_segment(text, clean_text):
    return clean_text(text)[:MAX_CAPTION_LENGTH].strip()


def append_segment(room, segment, now=None):
    now = float(now if now is not None else time.time())
    captions = room.get("captions", [])
    if not isinstance(captions, list):
        captions = []
    minimum_time = now - CAPTION_TTL_SECONDS
    captions = [
        item for item in captions
        if isinstance(item, dict) and float(item.get("created_at", 0) or 0) >= minimum_time
    ]
    captions.append(dict(segment))
    room["captions"] = captions[-MAX_ROOM_CAPTIONS:]
    return segment


def segments_after(room, after=0, exclude_email="", now=None):
    try:
        after = float(after or 0)
    except (TypeError, ValueError):
        after = 0
    exclude_email = str(exclude_email or "").strip().lower()
    minimum_time = float(now if now is not None else time.time()) - CAPTION_TTL_SECONDS
    result = []
    for item in room.get("captions", []) if isinstance(room.get("captions", []), list) else []:
        created_at = float(item.get("created_at", 0) or 0) if isinstance(item, dict) else 0
        if not isinstance(item, dict) or created_at <= after or created_at < minimum_time:
            continue
        if str(item.get("speaker_email", "")).strip().lower() == exclude_email:
            continue
        result.append(dict(item))
    return result


def caption_by_id(room, caption_id):
    caption_id = str(caption_id or "")
    for item in room.get("captions", []) if isinstance(room.get("captions", []), list) else []:
        if isinstance(item, dict) and str(item.get("id", "")) == caption_id:
            return dict(item)
    return None


def purge_temporary_data(room):
    """Remove all ephemeral caption/transcription state from a closed call room."""
    if not isinstance(room, dict):
        return False
    changed = False
    for key in TEMPORARY_CAPTION_KEYS:
        if key in room:
            room.pop(key, None)
            changed = True
    return changed
