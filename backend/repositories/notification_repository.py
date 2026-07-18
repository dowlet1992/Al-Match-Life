from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_NOTIFICATIONS_DATA = {"notifications": []}


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_notifications_data(data):
    if isinstance(data, dict):
        notifications = data.get("notifications", [])
        if isinstance(notifications, list):
            return {"notifications": notifications}
        return {"notifications": []}

    if isinstance(data, list):
        return {"notifications": data}

    return {"notifications": []}


class JsonNotificationRepository:
    def __init__(self, filename="notifications.json"):
        self.store = JsonStore(filename, DEFAULT_NOTIFICATIONS_DATA)

    def load_all(self):
        return normalize_notifications_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_notifications_data(data))


class PostgresNotificationRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT target.email, sender.email, n.type, n.text, n.status, n.read,
                   n.created_at, n.updated_at
            FROM notifications n
            JOIN users target ON target.id = n.user_id
            LEFT JOIN users sender ON sender.id = n.from_user_id
            ORDER BY n.created_at DESC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                notifications = []
                for row in cursor.fetchall():
                    target_email, from_email, type_value, text, status, read, created_at, updated_at = row
                    notifications.append({
                        "email": normalize_email(target_email),
                        "from": normalize_email(from_email),
                        "from_email": normalize_email(from_email),
                        "type": type_value or "system",
                        "text": text or "",
                        "status": status or "",
                        "read": read is True,
                        "created_at": str(created_at or ""),
                        "created_at_iso": str(created_at or ""),
                        "updated_at": str(updated_at or ""),
                    })
        return {"notifications": notifications}

    def save_all(self, data):
        data = normalize_notifications_data(data)
        query = """
            INSERT INTO notifications (
                user_id, from_user_id, type, text, status, read, created_at, updated_at
            )
            SELECT target.id, sender.id, %(type)s, %(text)s, %(status)s, %(read)s,
                   COALESCE(%(created_at)s::timestamptz, now()),
                   COALESCE(%(updated_at)s::timestamptz, now())
            FROM users target
            LEFT JOIN users sender ON sender.email = %(from_email)s
            WHERE target.email = %(email)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM notifications")
                for item in data["notifications"]:
                    if not isinstance(item, dict):
                        continue
                    email = normalize_email(item.get("email") or item.get("to"))
                    if not email:
                        continue
                    cursor.execute(query, {
                        "email": email,
                        "from_email": normalize_email(item.get("from_email") or item.get("from")),
                        "type": item.get("type", "system"),
                        "text": item.get("text", ""),
                        "status": item.get("status", ""),
                        "read": item.get("read") is True,
                        "created_at": item.get("created_at_iso") or item.get("created_at") or None,
                        "updated_at": item.get("updated_at") or None,
                    })
            connection.commit()


def get_notification_repository(filename="notifications.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "notifications.json":
        return PostgresNotificationRepository(client=client)
    return JsonNotificationRepository(filename)
