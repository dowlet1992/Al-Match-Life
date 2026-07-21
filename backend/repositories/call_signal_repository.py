from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore
from backend.services import call_quality_service
from datetime import datetime, timezone
import threading
import time
import hashlib


_JSON_CALL_SIGNAL_LOCK = threading.RLock()
CLOSED_CALL_STATUSES = {"ended", "declined", "missed"}
CALL_REOPEN_SIGNAL_TYPES = {"ringing"}
SIGNAL_RETENTION_SECONDS = 24 * 60 * 60
CLOSED_ROOM_RETENTION_SECONDS = 24 * 60 * 60
STALE_OPEN_ROOM_RETENTION_SECONDS = 7 * 24 * 60 * 60


def normalize_dict(data):
    return data if isinstance(data, dict) else {}


def can_append_signal(room, signal):
    if str(room.get("status", "")) not in CLOSED_CALL_STATUSES:
        return True
    return str(signal.get("type", "")) in CALL_REOPEN_SIGNAL_TYPES


def signal_participants(room, signal):
    participants = room.get("participants", [])
    participants = participants if isinstance(participants, list) else []
    participants = {str(email or "").strip().lower() for email in participants}
    participants.update({
        str(signal.get("from", "") or "").strip().lower(),
        str(signal.get("to", "") or "").strip().lower(),
    })
    return sorted(email for email in participants if email)


def room_has_participant(room, email):
    email = str(email or "").strip().lower()
    if not email or not isinstance(room, dict):
        return False
    participants = room.get("participants", [])
    participants = participants if isinstance(participants, list) else []
    if email in {str(item or "").strip().lower() for item in participants if item}:
        return True
    messages = room.get("messages", [])
    for message in messages if isinstance(messages, list) else []:
        if not isinstance(message, dict):
            continue
        if email in {
            str(message.get("from", "") or "").strip().lower(),
            str(message.get("to", "") or "").strip().lower(),
        }:
            return True
    return False


def compact_signal_messages(messages, now, max_messages=300):
    messages = messages if isinstance(messages, list) else []
    cutoff = float(now) - SIGNAL_RETENTION_SECONDS
    retained = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        try:
            created_at = float(message.get("created_at", 0) or 0)
        except (TypeError, ValueError):
            created_at = 0
        if created_at <= 0 or created_at >= cutoff:
            retained.append(dict(message))
    return retained[-max(int(max_messages or 1), 1):]


def room_last_activity(room):
    timestamps = []
    for message in room.get("messages", []) if isinstance(room.get("messages", []), list) else []:
        try:
            timestamps.append(float(message.get("created_at", 0) or 0))
        except (AttributeError, TypeError, ValueError):
            continue
    if timestamps:
        return max(timestamps)
    updated_at = str(room.get("updated_at", "") or "").strip()
    if updated_at:
        try:
            parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            pass
    return 0


def latest_quality_sample_time(samples, participant):
    latest = 0
    for item in samples if isinstance(samples, list) else []:
        if not isinstance(item, dict) or str(item.get("participant_email", "")) != participant:
            continue
        try:
            latest = max(latest, float(item.get("created_at", 0) or 0))
        except (TypeError, ValueError):
            continue
    return latest


def signal_rate_exceeded(messages, signal, now, limit, window_seconds):
    if not limit:
        return False
    cutoff = float(now) - max(float(window_seconds), 1)
    signal_type = str(signal.get("type", ""))
    sender = str(signal.get("from", "")).strip().lower()
    count = 0
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            created_at = float(item.get("created_at", 0) or 0)
        except (TypeError, ValueError):
            continue
        if created_at >= cutoff and str(item.get("type", "")) == signal_type and str(item.get("from", "")).strip().lower() == sender:
            count += 1
    return count >= max(int(limit), 1)


def latest_signal(messages, signal_type):
    for item in reversed(messages if isinstance(messages, list) else []):
        if isinstance(item, dict) and str(item.get("type", "")) == signal_type:
            return item
    return None


def duplicate_signal_room(room, signal):
    signal_id = str(signal.get("id", ""))
    if not signal_id:
        return None
    messages = room.get("messages", []) if isinstance(room, dict) else []
    for item in messages if isinstance(messages, list) else []:
        if not isinstance(item, dict) or str(item.get("id", "")) != signal_id:
            continue
        comparable_fields = ("type", "from", "to", "payload")
        if any(item.get(field) != signal.get(field) for field in comparable_fields):
            return "idempotency_conflict"
        result = dict(room)
        result["_signal_duplicate"] = True
        return result
    return None


def valid_signal_transition(room, signal):
    messages = room.get("messages", []) if isinstance(room, dict) else []
    messages = messages if isinstance(messages, list) else []
    signal_type = str(signal.get("type", ""))
    sender = str(signal.get("from", "")).strip().lower()
    receiver = str(signal.get("to", "")).strip().lower()
    if signal_type == "ringing":
        return not messages
    ringing = latest_signal(messages, "ringing")
    if ringing is None:
        return False
    ringing_from = str(ringing.get("from", "")).strip().lower()
    ringing_to = str(ringing.get("to", "")).strip().lower()
    if signal_type == "offer":
        return sender == ringing_from and receiver == ringing_to
    if signal_type == "accepted":
        return sender == ringing_to and receiver == ringing_from and latest_signal(messages, "accepted") is None
    if signal_type == "answer":
        offer = latest_signal(messages, "offer")
        return bool(offer) and sender == str(offer.get("to", "")).strip().lower() and receiver == str(offer.get("from", "")).strip().lower()
    if signal_type == "ice":
        return latest_signal(messages, "offer") is not None
    if signal_type == "declined":
        return sender == ringing_to and receiver == ringing_from and latest_signal(messages, "accepted") is None
    if signal_type == "ended":
        return True
    if signal_type == "missed":
        return latest_signal(messages, "accepted") is None
    return False


def timeout_transition(room_id, room, now, ringing_timeout=45, negotiation_timeout=30):
    if not isinstance(room, dict) or room.get("status") in CLOSED_CALL_STATUSES:
        return None
    messages = room.get("messages", []) if isinstance(room.get("messages", []), list) else []
    ringing = latest_signal(messages, "ringing")
    if ringing is None or latest_signal(messages, "answer") is not None:
        return None
    accepted = latest_signal(messages, "accepted")
    reference = accepted if accepted is not None else ringing
    try:
        age = float(now) - float(reference.get("created_at", 0) or 0)
    except (TypeError, ValueError):
        return None
    if accepted is not None and age >= max(float(negotiation_timeout), 1):
        event_type = "ended"
        reason = "negotiation_timeout"
    elif accepted is None and age >= max(float(ringing_timeout), 1):
        event_type = "missed"
        reason = "ringing_timeout"
    else:
        return None
    seed = f"{room_id}::{reason}::{reference.get('created_at', 0)}"
    ringing_payload = ringing.get("payload", {}) if isinstance(ringing.get("payload"), dict) else {}
    return {
        "id": "timeout_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32],
        "type": event_type,
        "from": str(ringing.get("from", "")),
        "to": str(ringing.get("to", "")),
        "payload": {"call_type": ringing_payload.get("call_type", "audio"), "reason": reason},
        "created_at": float(now),
    }


def call_cancel_push_event(room_id, room, transition, now):
    messages = room.get("messages", []) if isinstance(room, dict) else []
    ringing = latest_signal(messages, "ringing")
    if not isinstance(ringing, dict) or not isinstance(transition, dict):
        return None
    ringing_payload = ringing.get("payload", {}) if isinstance(ringing.get("payload"), dict) else {}
    seed = f"{room_id}::{transition.get('id', '')}::call_cancelled"
    return {
        "event_id": "cancel_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32],
        "target_email": str(ringing.get("to", "")).strip().lower(),
        "event_type": "call_cancelled",
        "payload": {
            "call_id": str(room_id),
            "call_type": ringing_payload.get("call_type", "audio"),
            "caller_email": str(ringing.get("from", "")).strip().lower(),
            "receiver_email": str(ringing.get("to", "")).strip().lower(),
        },
        "created_at": float(now),
        "expires_at": float(now) + 120,
        "attempts": 0,
        "status": "pending",
    }


def append_json_push_event(room, event):
    if not isinstance(event, dict):
        return
    outbox = room.get("push_outbox", []) if isinstance(room.get("push_outbox"), list) else []
    if not any(isinstance(item, dict) and item.get("event_id") == event.get("event_id") for item in outbox):
        room["push_outbox"] = [*outbox, dict(event)][-50:]


def insert_postgres_push_event(cursor, room_id, event):
    if not isinstance(event, dict):
        return
    cursor.execute("""
        INSERT INTO call_push_outbox (event_id, target_user_id, room_id, event_type, payload, expires_at)
        SELECT %(event_id)s, id, %(room_id)s, %(event_type)s, %(event_payload)s, to_timestamp(%(expires_at)s)
        FROM users WHERE email = %(target_email)s ON CONFLICT (event_id) DO NOTHING
    """, {
        "event_id": str(event.get("event_id", "")), "target_email": str(event.get("target_email", "")).strip().lower(),
        "room_id": str(room_id), "event_type": str(event.get("event_type", "incoming_call")),
        "event_payload": event.get("payload", {}), "expires_at": float(event.get("expires_at", time.time() + 45)),
    })


class JsonCallSignalRepository:
    def __init__(self, filename="call_signals.json"):
        self.store = JsonStore(filename, {})

    def load_all(self):
        with _JSON_CALL_SIGNAL_LOCK:
            return normalize_dict(self.store.load())

    def save_all(self, data):
        with _JSON_CALL_SIGNAL_LOCK:
            self.store.save(normalize_dict(data))

    def get_room(self, room_id):
        with _JSON_CALL_SIGNAL_LOCK:
            room = normalize_dict(self.store.load()).get(str(room_id))
            return dict(room) if isinstance(room, dict) else None

    def append_signal(self, room_id, signal, status="active", updated_at="", max_messages=300, close=False, rate_limit=None, rate_window=60, enforce_transition=False, push_event=None):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            room = dict(room) if isinstance(room, dict) else {}
            duplicate = duplicate_signal_room(room, signal)
            if duplicate == "idempotency_conflict":
                return duplicate
            if duplicate is not None:
                return duplicate
            if not can_append_signal(room, signal):
                return "invalid_transition" if enforce_transition else None
            reopening = room.get("status") in CLOSED_CALL_STATUSES
            if reopening:
                room.pop("accepted_at", None)
                room.pop("quality_summary", None)
                room["messages"] = []
            if enforce_transition and not valid_signal_transition(room, signal):
                return "invalid_transition"
            now = float(signal.get("created_at", time.time()) or time.time())
            if signal_rate_exceeded(room.get("messages", []), signal, now, rate_limit, rate_window):
                return "rate_limited"
            messages = compact_signal_messages(room.get("messages", []), now, max_messages=max_messages)
            messages.append(dict(signal))
            room["messages"] = messages[-max(int(max_messages or 1), 1):]
            if isinstance(push_event, dict):
                append_json_push_event(room, push_event)
            participants = signal_participants(room, signal)
            if participants:
                room["participants"] = participants
            room["status"] = str(status or "active")
            room["updated_at"] = str(updated_at or "")
            if str(signal.get("type", "")) == "accepted":
                room["accepted_at"] = now
            if close:
                if isinstance(room.get("quality_samples"), list) and room["quality_samples"]:
                    room["quality_summary"] = call_quality_service.summarize_samples(room["quality_samples"])
                room.pop("captions", None)
                room.pop("transcription_reservations", None)
                room.pop("quality_samples", None)
            data[str(room_id)] = room
            self.store.save(data)
            return dict(room)

    def prune_expired(self, now=None, closed_retention=CLOSED_ROOM_RETENTION_SECONDS, stale_retention=STALE_OPEN_ROOM_RETENTION_SECONDS):
        now = float(now if now is not None else time.time())
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            retained = {}
            for room_id, room in data.items():
                if not isinstance(room, dict):
                    continue
                age = now - room_last_activity(room)
                retention = closed_retention if room.get("status") in CLOSED_CALL_STATUSES else stale_retention
                if age <= max(float(retention), 1):
                    retained[room_id] = room
            deleted_count = len(data) - len(retained)
            if deleted_count:
                self.store.save(retained)
            return deleted_count

    def delete_for_participant(self, email):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            retained = {
                room_id: room for room_id, room in data.items()
                if not room_has_participant(room, email)
            }
            deleted_count = len(data) - len(retained)
            if deleted_count:
                self.store.save(retained)
            return deleted_count

    def append_caption(self, room_id, segment, max_items=120, minimum_created_at=0):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict):
                return "missing"
            if room.get("status") not in {"active", "accepted", "ringing"}:
                return "inactive"
            captions = room.get("captions", [])
            captions = captions if isinstance(captions, list) else []
            captions = [
                item for item in captions
                if isinstance(item, dict) and float(item.get("created_at", 0) or 0) >= float(minimum_created_at or 0)
            ]
            captions.append(dict(segment))
            room["captions"] = captions[-max(int(max_items or 1), 1):]
            data[str(room_id)] = room
            self.store.save(data)
            return "appended"

    def append_quality_sample(self, room_id, sample, max_items=24, minimum_interval=4):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict) or room.get("status") not in {"active", "accepted", "ringing"}:
                return "inactive"
            samples = room.get("quality_samples", [])
            samples = samples if isinstance(samples, list) else []
            participant = str(sample.get("participant_email", ""))
            latest = latest_quality_sample_time(samples, participant)
            if latest and float(sample.get("created_at", 0) or 0) - latest < max(float(minimum_interval), 0):
                return "rate_limited"
            samples.append(dict(sample))
            room["quality_samples"] = samples[-max(int(max_items or 1), 1):]
            self.store.save(data)
            return "appended"

    def acknowledge_signals(self, room_id, receiver_email, event_ids, acknowledged_at):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict):
                return "missing", 0
            receiver_email = str(receiver_email or "").strip().lower()
            event_ids = {str(event_id) for event_id in event_ids}
            acknowledged = 0
            changed = False
            for message in room.get("messages", []) if isinstance(room.get("messages", []), list) else []:
                if not isinstance(message, dict) or str(message.get("id", "")) not in event_ids:
                    continue
                if str(message.get("to", "")).strip().lower() != receiver_email:
                    continue
                acknowledged += 1
                if str(message.get("acknowledged_by", "")).strip().lower() != receiver_email:
                    message["acknowledged_by"] = receiver_email
                    message["acknowledged_at"] = float(acknowledged_at)
                    changed = True
            if changed:
                self.store.save(data)
            return "acknowledged", acknowledged

    def expire_room(self, room_id, now, ringing_timeout=45, negotiation_timeout=30):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict):
                return None
            transition = timeout_transition(room_id, room, now, ringing_timeout, negotiation_timeout)
            if transition is None:
                return {"transition": None, "room": dict(room)}
            messages = room.get("messages", []) if isinstance(room.get("messages", []), list) else []
            room["messages"] = [*messages, transition][-300:]
            room["status"] = transition["type"]
            append_json_push_event(room, call_cancel_push_event(room_id, room, transition, now))
            room["updated_at"] = datetime.fromtimestamp(float(now), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(room.get("quality_samples"), list) and room["quality_samples"]:
                room["quality_summary"] = call_quality_service.summarize_samples(room["quality_samples"])
            room.pop("captions", None)
            room.pop("transcription_reservations", None)
            room.pop("quality_samples", None)
            self.store.save(data)
            return {"transition": dict(transition), "room": dict(room)}

    def expire_due_rooms(self, now, ringing_timeout=45, negotiation_timeout=30, batch_size=200):
        results = []
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            changed = False
            candidates = (
                (room_id, room) for room_id, room in data.items()
                if isinstance(room, dict)
                and room.get("status") not in CLOSED_CALL_STATUSES
                and latest_signal(room.get("messages", []), "answer") is None
            )
            for room_id, room in list(candidates)[:max(int(batch_size), 1)]:
                transition = timeout_transition(room_id, room, now, ringing_timeout, negotiation_timeout)
                if transition is None:
                    continue
                messages = room.get("messages", []) if isinstance(room.get("messages", []), list) else []
                room["messages"] = [*messages, transition][-300:]
                room["status"] = transition["type"]
                append_json_push_event(room, call_cancel_push_event(room_id, room, transition, now))
                room["updated_at"] = datetime.fromtimestamp(float(now), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(room.get("quality_samples"), list) and room["quality_samples"]:
                    room["quality_summary"] = call_quality_service.summarize_samples(room["quality_samples"])
                room.pop("captions", None)
                room.pop("transcription_reservations", None)
                room.pop("quality_samples", None)
                results.append({"transition": dict(transition), "room": dict(room)})
                changed = True
            if changed:
                self.store.save(data)
        return results

    def set_caption_translation(self, room_id, caption_id, language, translated_text):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict):
                return "missing"
            for caption in room.get("captions", []) if isinstance(room.get("captions", []), list) else []:
                if isinstance(caption, dict) and str(caption.get("id", "")) == str(caption_id):
                    translations = caption.get("translations", {})
                    translations = translations if isinstance(translations, dict) else {}
                    translations[str(language)] = str(translated_text)
                    caption["translations"] = translations
                    self.store.save(data)
                    return "updated"
            return "missing"

    def reserve_transcription(self, room_id, speaker_email, sequence, now, window_seconds=60, limit=18):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict) or room.get("status") not in {"active", "accepted", "ringing"}:
                return "inactive"
            reservations = room.get("transcription_reservations", [])
            reservations = reservations if isinstance(reservations, list) else []
            cutoff = float(now) - max(int(window_seconds), 1)
            reservations = [item for item in reservations if isinstance(item, dict) and float(item.get("created_at", 0)) >= cutoff]
            speaker_email = str(speaker_email).lower()
            if any(str(item.get("speaker_email", "")).lower() == speaker_email and int(item.get("sequence", 0)) == int(sequence) for item in reservations):
                return "duplicate"
            if sum(1 for item in reservations if str(item.get("speaker_email", "")).lower() == speaker_email) >= max(int(limit), 1):
                return "rate_limited"
            reservations.append({"speaker_email": speaker_email, "sequence": int(sequence), "created_at": float(now)})
            room["transcription_reservations"] = reservations[-100:]
            self.store.save(data)
            return "reserved"

    def purge_caption_data(self, room_id):
        with _JSON_CALL_SIGNAL_LOCK:
            data = normalize_dict(self.store.load())
            room = data.get(str(room_id))
            if not isinstance(room, dict):
                return False
            changed = False
            for key in ("captions", "transcription_reservations", "quality_samples"):
                if key in room:
                    room.pop(key, None)
                    changed = True
            if changed:
                self.store.save(data)
            return changed


class PostgresCallSignalRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = "SELECT room_id, payload, updated_at FROM call_signals ORDER BY updated_at ASC"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return {
                    room_id: {
                        **(payload if isinstance(payload, dict) else {}),
                        "updated_at": str(updated_at or ""),
                    }
                    for room_id, payload, updated_at in cursor.fetchall()
                }

    def save_all(self, data):
        data = normalize_dict(data)
        query = """
            INSERT INTO call_signals (room_id, payload, updated_at)
            VALUES (%(room_id)s, %(payload)s, now())
            ON CONFLICT (room_id) DO UPDATE SET
                payload = EXCLUDED.payload,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM call_signals")
                for room_id, payload in data.items():
                    cursor.execute(query, {
                        "room_id": str(room_id),
                        "payload": payload if isinstance(payload, dict) else {},
                    })
            connection.commit()

    def get_room(self, room_id):
        query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"room_id": str(room_id)})
                row = cursor.fetchone()
        return dict(row[0]) if row and isinstance(row[0], dict) else None

    def append_signal(self, room_id, signal, status="active", updated_at="", max_messages=300, close=False, rate_limit=None, rate_window=60, enforce_transition=False, push_event=None):
        insert_query = """
            INSERT INTO call_signals (room_id, payload, updated_at)
            VALUES (%(room_id)s, %(payload)s, now())
            ON CONFLICT (room_id) DO NOTHING
        """
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        room_id = str(room_id)
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                if enforce_transition and str(signal.get("type", "")) != "ringing":
                    cursor.execute(select_query, {"room_id": room_id})
                else:
                    cursor.execute(insert_query, {"room_id": room_id, "payload": {}})
                    cursor.execute(select_query, {"room_id": room_id})
                row = cursor.fetchone()
                if enforce_transition and (not row or not isinstance(row[0], dict)):
                    return "invalid_transition"
                payload = dict(row[0]) if row and isinstance(row[0], dict) else {}
                duplicate = duplicate_signal_room(payload, signal)
                if duplicate == "idempotency_conflict":
                    return duplicate
                if duplicate is not None:
                    return duplicate
                if not can_append_signal(payload, signal):
                    return "invalid_transition" if enforce_transition else None
                reopening = payload.get("status") in CLOSED_CALL_STATUSES
                if reopening:
                    payload.pop("accepted_at", None)
                    payload.pop("quality_summary", None)
                    payload["messages"] = []
                if enforce_transition and not valid_signal_transition(payload, signal):
                    return "invalid_transition"
                now = float(signal.get("created_at", time.time()) or time.time())
                if signal_rate_exceeded(payload.get("messages", []), signal, now, rate_limit, rate_window):
                    return "rate_limited"
                messages = compact_signal_messages(payload.get("messages", []), now, max_messages=max_messages)
                messages.append(dict(signal))
                payload["messages"] = messages[-max(int(max_messages or 1), 1):]
                participants = signal_participants(payload, signal)
                if participants:
                    payload["participants"] = participants
                payload["status"] = str(status or "active")
                payload["updated_at"] = str(updated_at or "")
                if str(signal.get("type", "")) == "accepted":
                    payload["accepted_at"] = now
                if close:
                    if isinstance(payload.get("quality_samples"), list) and payload["quality_samples"]:
                        payload["quality_summary"] = call_quality_service.summarize_samples(payload["quality_samples"])
                    payload.pop("captions", None)
                    payload.pop("transcription_reservations", None)
                    payload.pop("quality_samples", None)
                cursor.execute(update_query, {"room_id": room_id, "payload": payload})
                if isinstance(push_event, dict):
                    insert_postgres_push_event(cursor, room_id, push_event)
            connection.commit()
        return payload

    def prune_expired(self, now=None, closed_retention=CLOSED_ROOM_RETENTION_SECONDS, stale_retention=STALE_OPEN_ROOM_RETENTION_SECONDS):
        now = float(now if now is not None else time.time())
        query = """
            DELETE FROM call_signals
            WHERE (payload->>'status' IN ('ended', 'declined', 'missed') AND updated_at < %(closed_before)s)
               OR (COALESCE(payload->>'status', 'active') NOT IN ('ended', 'declined', 'missed') AND updated_at < %(stale_before)s)
        """
        params = {
            "closed_before": datetime.fromtimestamp(now - max(float(closed_retention), 1), tz=timezone.utc),
            "stale_before": datetime.fromtimestamp(now - max(float(stale_retention), 1), tz=timezone.utc),
        }
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                deleted_count = getattr(cursor, "rowcount", 0)
            connection.commit()
        return max(int(deleted_count or 0), 0)

    def delete_for_participant(self, email):
        query = """
            DELETE FROM call_signals
            WHERE lower(%(email)s) = ANY (
                SELECT lower(value)
                FROM jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(payload->'participants') = 'array' THEN payload->'participants'
                        ELSE '[]'::jsonb
                    END
                )
            )
            OR EXISTS (
                SELECT 1
                FROM jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(payload->'messages') = 'array' THEN payload->'messages'
                        ELSE '[]'::jsonb
                    END
                ) AS message
                WHERE lower(COALESCE(message->>'from', '')) = lower(%(email)s)
                   OR lower(COALESCE(message->>'to', '')) = lower(%(email)s)
            )
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"email": str(email or "").strip().lower()})
                deleted_count = getattr(cursor, "rowcount", 0)
            connection.commit()
        return max(int(deleted_count or 0), 0)

    def append_caption(self, room_id, segment, max_items=120, minimum_created_at=0):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return "missing"
                payload = dict(row[0])
                if payload.get("status") not in {"active", "accepted", "ringing"}:
                    return "inactive"
                captions = payload.get("captions", [])
                captions = captions if isinstance(captions, list) else []
                captions = [
                    item for item in captions
                    if isinstance(item, dict) and float(item.get("created_at", 0) or 0) >= float(minimum_created_at or 0)
                ]
                captions.append(dict(segment))
                payload["captions"] = captions[-max(int(max_items or 1), 1):]
                cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
            connection.commit()
        return "appended"

    def append_quality_sample(self, room_id, sample, max_items=24, minimum_interval=4):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return "inactive"
                payload = dict(row[0])
                if payload.get("status") not in {"active", "accepted", "ringing"}:
                    return "inactive"
                samples = payload.get("quality_samples", [])
                samples = samples if isinstance(samples, list) else []
                participant = str(sample.get("participant_email", ""))
                latest = latest_quality_sample_time(samples, participant)
                if latest and float(sample.get("created_at", 0) or 0) - latest < max(float(minimum_interval), 0):
                    return "rate_limited"
                samples.append(dict(sample))
                payload["quality_samples"] = samples[-max(int(max_items or 1), 1):]
                cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
            connection.commit()
        return "appended"

    def acknowledge_signals(self, room_id, receiver_email, event_ids, acknowledged_at):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return "missing", 0
                payload = dict(row[0])
                receiver_email = str(receiver_email or "").strip().lower()
                event_ids = {str(event_id) for event_id in event_ids}
                acknowledged = 0
                changed = False
                for message in payload.get("messages", []) if isinstance(payload.get("messages", []), list) else []:
                    if not isinstance(message, dict) or str(message.get("id", "")) not in event_ids:
                        continue
                    if str(message.get("to", "")).strip().lower() != receiver_email:
                        continue
                    acknowledged += 1
                    if str(message.get("acknowledged_by", "")).strip().lower() != receiver_email:
                        message["acknowledged_by"] = receiver_email
                        message["acknowledged_at"] = float(acknowledged_at)
                        changed = True
                if changed:
                    cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
            connection.commit()
        return "acknowledged", acknowledged

    def expire_room(self, room_id, now, ringing_timeout=45, negotiation_timeout=30):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return None
                payload = dict(row[0])
                transition = timeout_transition(room_id, payload, now, ringing_timeout, negotiation_timeout)
                if transition is None:
                    return {"transition": None, "room": payload}
                messages = payload.get("messages", []) if isinstance(payload.get("messages", []), list) else []
                payload["messages"] = [*messages, transition][-300:]
                payload["status"] = transition["type"]
                payload["updated_at"] = datetime.fromtimestamp(float(now), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(payload.get("quality_samples"), list) and payload["quality_samples"]:
                    payload["quality_summary"] = call_quality_service.summarize_samples(payload["quality_samples"])
                payload.pop("captions", None)
                payload.pop("transcription_reservations", None)
                payload.pop("quality_samples", None)
                cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
                insert_postgres_push_event(cursor, room_id, call_cancel_push_event(room_id, payload, transition, now))
            connection.commit()
        return {"transition": dict(transition), "room": payload}

    def expire_due_rooms(self, now, ringing_timeout=45, negotiation_timeout=30, batch_size=200):
        select_query = """
            SELECT room_id, payload FROM call_signals
            WHERE COALESCE(payload->>'status', 'active') NOT IN ('ended', 'declined', 'missed')
              AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(
                      CASE WHEN jsonb_typeof(payload->'messages') = 'array'
                           THEN payload->'messages' ELSE '[]'::jsonb END
                  ) AS message
                  WHERE message->>'type' = 'answer'
              )
            ORDER BY updated_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT %(batch_size)s
        """
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        results = []
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"batch_size": max(int(batch_size), 1)})
                rows = cursor.fetchall()
                for room_id, stored_payload in rows:
                    if not isinstance(stored_payload, dict):
                        continue
                    payload = dict(stored_payload)
                    transition = timeout_transition(room_id, payload, now, ringing_timeout, negotiation_timeout)
                    if transition is None:
                        continue
                    messages = payload.get("messages", []) if isinstance(payload.get("messages", []), list) else []
                    payload["messages"] = [*messages, transition][-300:]
                    payload["status"] = transition["type"]
                    payload["updated_at"] = datetime.fromtimestamp(float(now), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    if isinstance(payload.get("quality_samples"), list) and payload["quality_samples"]:
                        payload["quality_summary"] = call_quality_service.summarize_samples(payload["quality_samples"])
                    payload.pop("captions", None)
                    payload.pop("transcription_reservations", None)
                    payload.pop("quality_samples", None)
                    cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
                    insert_postgres_push_event(cursor, room_id, call_cancel_push_event(room_id, payload, transition, now))
                    results.append({"transition": dict(transition), "room": payload})
            connection.commit()
        return results

    def set_caption_translation(self, room_id, caption_id, language, translated_text):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return "missing"
                payload = dict(row[0])
                found = False
                for caption in payload.get("captions", []) if isinstance(payload.get("captions", []), list) else []:
                    if isinstance(caption, dict) and str(caption.get("id", "")) == str(caption_id):
                        translations = caption.get("translations", {})
                        translations = translations if isinstance(translations, dict) else {}
                        translations[str(language)] = str(translated_text)
                        caption["translations"] = translations
                        found = True
                        break
                if not found:
                    return "missing"
                cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
            connection.commit()
        return "updated"

    def reserve_transcription(self, room_id, speaker_email, sequence, now, window_seconds=60, limit=18):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return "inactive"
                payload = dict(row[0])
                if payload.get("status") not in {"active", "accepted", "ringing"}:
                    return "inactive"
                reservations = payload.get("transcription_reservations", [])
                reservations = reservations if isinstance(reservations, list) else []
                cutoff = float(now) - max(int(window_seconds), 1)
                reservations = [item for item in reservations if isinstance(item, dict) and float(item.get("created_at", 0)) >= cutoff]
                speaker_email = str(speaker_email).lower()
                if any(str(item.get("speaker_email", "")).lower() == speaker_email and int(item.get("sequence", 0)) == int(sequence) for item in reservations):
                    return "duplicate"
                if sum(1 for item in reservations if str(item.get("speaker_email", "")).lower() == speaker_email) >= max(int(limit), 1):
                    return "rate_limited"
                reservations.append({"speaker_email": speaker_email, "sequence": int(sequence), "created_at": float(now)})
                payload["transcription_reservations"] = reservations[-100:]
                cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
            connection.commit()
        return "reserved"

    def purge_caption_data(self, room_id):
        select_query = "SELECT payload FROM call_signals WHERE room_id = %(room_id)s FOR UPDATE"
        update_query = "UPDATE call_signals SET payload = %(payload)s, updated_at = now() WHERE room_id = %(room_id)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"room_id": str(room_id)})
                row = cursor.fetchone()
                if not row or not isinstance(row[0], dict):
                    return False
                payload = dict(row[0])
                changed = False
                for key in ("captions", "transcription_reservations", "quality_samples"):
                    if key in payload:
                        payload.pop(key, None)
                        changed = True
                if changed:
                    cursor.execute(update_query, {"room_id": str(room_id), "payload": payload})
            connection.commit()
        return changed


def get_call_signal_repository(filename="call_signals.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "call_signals.json":
        return PostgresCallSignalRepository(client=client)
    return JsonCallSignalRepository(filename)
