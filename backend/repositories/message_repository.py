from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


MESSAGE_COLUMNS = [
    "id",
    "sender_email",
    "receiver_email",
    "message",
    "media_url",
    "media_type",
    "media_name",
    "reply_to",
    "status",
    "deleted_for_everyone",
    "deleted_for",
    "source_language",
    "translations",
    "created_at",
]


def normalize_email(value):
    return str(value or "").strip().lower()


def message_from_record(record):
    if isinstance(record, dict):
        return dict(record)

    values = dict(zip(MESSAGE_COLUMNS, record))
    return {
        "id": values.get("id"),
        "from": normalize_email(values.get("sender_email")),
        "to": normalize_email(values.get("receiver_email")),
        "message": values.get("message", ""),
        "media_url": values.get("media_url", ""),
        "media_type": values.get("media_type", ""),
        "media_name": values.get("media_name", ""),
        "reply_to": values.get("reply_to") or "",
        "status": values.get("status", "sent"),
        "deleted_for_everyone": values.get("deleted_for_everyone") is True,
        "deleted_for": values.get("deleted_for") if isinstance(values.get("deleted_for"), list) else [],
        "source_language": values.get("source_language") or "unknown",
        "translations": values.get("translations") if isinstance(values.get("translations"), dict) else {},
        "time": str(values.get("created_at") or ""),
    }


def message_to_database_params(message):
    return {
        "id": message.get("id"),
        "sender_email": normalize_email(message.get("from")),
        "receiver_email": normalize_email(message.get("to")),
        "message": message.get("message", ""),
        "media_url": message.get("media_url", ""),
        "media_type": message.get("media_type", ""),
        "media_name": message.get("media_name", ""),
        "reply_to": message.get("reply_to") or None,
        "status": message.get("status", "sent"),
        "deleted_for_everyone": message.get("deleted_for_everyone") is True,
        "deleted_for": message.get("deleted_for") if isinstance(message.get("deleted_for"), list) else [],
        "source_language": message.get("source_language") or "unknown",
        "translations": message.get("translations") if isinstance(message.get("translations"), dict) else {},
        "created_at": message.get("created_at") or message.get("time") or None,
    }


class JsonMessageRepository:
    def __init__(self, filename="messages.json"):
        self.store = JsonStore(filename, [])

    def load_all(self):
        data = self.store.load()
        if not isinstance(data, list):
            return []
        return data

    def save_all(self, messages):
        if not isinstance(messages, list):
            messages = []
        self.store.save(messages)


class PostgresMessageRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT m.id, sender.email, receiver.email, m.message, m.media_url, m.media_type,
                   m.media_name, m.reply_to, m.status, m.deleted_for_everyone,
                   m.deleted_for, m.source_language, m.translations, m.created_at
            FROM messages m
            JOIN users sender ON sender.id = m.sender_id
            JOIN users receiver ON receiver.id = m.receiver_id
            ORDER BY m.created_at ASC, m.id ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [message_from_record(row) for row in cursor.fetchall()]

    def save_all(self, messages):
        query = """
            INSERT INTO messages (
                id, sender_id, receiver_id, message, media_url, media_type, media_name,
                reply_to, status, deleted_for_everyone, deleted_for, source_language,
                translations, created_at
            )
            VALUES (
                %(id)s,
                (SELECT id FROM users WHERE email = %(sender_email)s),
                (SELECT id FROM users WHERE email = %(receiver_email)s),
                %(message)s, %(media_url)s, %(media_type)s, %(media_name)s,
                %(reply_to)s, %(status)s, %(deleted_for_everyone)s, %(deleted_for)s,
                %(source_language)s, %(translations)s,
                COALESCE(%(created_at)s::timestamptz, now())
            )
            ON CONFLICT (id) DO UPDATE SET
                message = EXCLUDED.message,
                media_url = EXCLUDED.media_url,
                media_type = EXCLUDED.media_type,
                media_name = EXCLUDED.media_name,
                reply_to = EXCLUDED.reply_to,
                status = EXCLUDED.status,
                deleted_for_everyone = EXCLUDED.deleted_for_everyone,
                deleted_for = EXCLUDED.deleted_for,
                source_language = EXCLUDED.source_language,
                translations = EXCLUDED.translations,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                for message in messages if isinstance(messages, list) else []:
                    cursor.execute(query, message_to_database_params(message))
            connection.commit()


def get_message_repository(filename="messages.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "messages.json":
        return PostgresMessageRepository(client=client)
    return JsonMessageRepository(filename)
