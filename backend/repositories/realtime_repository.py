from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


def normalize_dict(data):
    return data if isinstance(data, dict) else {}


class JsonRealtimeRepository:
    def __init__(self, typing_filename="typing_status.json", presence_filename="presence_status.json"):
        self.typing_store = JsonStore(typing_filename, {})
        self.presence_store = JsonStore(presence_filename, {})

    def load_typing_status(self):
        return normalize_dict(self.typing_store.load())

    def save_typing_status(self, data):
        self.typing_store.save(normalize_dict(data))

    def load_presence_status(self):
        return normalize_dict(self.presence_store.load())

    def save_presence_status(self, data):
        self.presence_store.save(normalize_dict(data))


class PostgresRealtimeRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_typing_status(self):
        query = """
            SELECT sender.email, receiver.email, is_typing, updated_at
            FROM realtime_typing rt
            JOIN users sender ON sender.id = rt.sender_id
            JOIN users receiver ON receiver.id = rt.receiver_id
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return {
                    f"{sender}::{receiver}": {"is_typing": is_typing is True, "updated_at": str(updated_at or "")}
                    for sender, receiver, is_typing, updated_at in cursor.fetchall()
                }

    def save_typing_status(self, data):
        data = normalize_dict(data)
        query = """
            INSERT INTO realtime_typing (sender_id, receiver_id, is_typing, updated_at)
            SELECT sender.id, receiver.id, %(is_typing)s, now()
            FROM users sender
            JOIN users receiver ON receiver.email = %(receiver)s
            WHERE sender.email = %(sender)s
            ON CONFLICT (sender_id, receiver_id) DO UPDATE SET
                is_typing = EXCLUDED.is_typing,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM realtime_typing")
                for key, value in data.items():
                    sender, receiver = split_pair_key(key)
                    if not sender or not receiver:
                        continue
                    cursor.execute(query, {
                        "sender": sender,
                        "receiver": receiver,
                        "is_typing": value.get("is_typing", value) is True if isinstance(value, dict) else value is True,
                    })
            connection.commit()

    def load_presence_status(self):
        query = """
            SELECT u.email, p.online, p.last_seen_at, p.updated_at
            FROM realtime_presence p
            JOIN users u ON u.id = p.user_id
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return {
                    email: {
                        "online": online is True,
                        "last_seen": str(last_seen_at or ""),
                        "updated_at": str(updated_at or ""),
                    }
                    for email, online, last_seen_at, updated_at in cursor.fetchall()
                }

    def save_presence_status(self, data):
        data = normalize_dict(data)
        query = """
            INSERT INTO realtime_presence (user_id, online, last_seen_at, updated_at)
            SELECT users.id, %(online)s, COALESCE(%(last_seen)s::timestamptz, now()), now()
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT (user_id) DO UPDATE SET
                online = EXCLUDED.online,
                last_seen_at = EXCLUDED.last_seen_at,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM realtime_presence")
                for email, value in data.items():
                    if not isinstance(value, dict):
                        value = {"online": bool(value)}
                    cursor.execute(query, {
                        "email": str(email).strip().lower(),
                        "online": value.get("online") is True,
                        "last_seen": value.get("last_seen") or value.get("last_seen_at") or None,
                    })
            connection.commit()


def split_pair_key(key):
    parts = str(key or "").split("::", 1)
    if len(parts) == 2:
        return parts[0].strip().lower(), parts[1].strip().lower()
    return "", ""


def get_realtime_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresRealtimeRepository(client=client)
    return JsonRealtimeRepository()
