from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


def normalize_dict(data):
    return data if isinstance(data, dict) else {}


def normalize_list(data):
    return data if isinstance(data, list) else []


class JsonSecurityRepository:
    def __init__(self, attempts_filename="login_attempts.json", events_filename="security_log.json"):
        self.attempts_store = JsonStore(attempts_filename, {})
        self.events_store = JsonStore(events_filename, [])

    def load_login_attempts(self):
        return normalize_dict(self.attempts_store.load())

    def save_login_attempts(self, data):
        self.attempts_store.save(normalize_dict(data))

    def load_security_events(self):
        return normalize_list(self.events_store.load())

    def save_security_events(self, events):
        self.events_store.save(normalize_list(events))


class PostgresSecurityRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_login_attempts(self):
        query = "SELECT key, attempts, locked_until FROM login_attempts ORDER BY updated_at ASC"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return {
                    key: {
                        "attempts": attempts if isinstance(attempts, list) else [],
                        "locked_until": str(locked_until or ""),
                    }
                    for key, attempts, locked_until in cursor.fetchall()
                }

    def save_login_attempts(self, data):
        data = normalize_dict(data)
        query = """
            INSERT INTO login_attempts (key, email, ip, attempts, locked_until, updated_at)
            VALUES (%(key)s, %(email)s, %(ip)s, %(attempts)s, %(locked_until)s, now())
            ON CONFLICT (key) DO UPDATE SET
                attempts = EXCLUDED.attempts,
                locked_until = EXCLUDED.locked_until,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM login_attempts")
                for key, value in data.items():
                    if not isinstance(value, dict):
                        continue
                    email, ip = split_attempt_key(key)
                    cursor.execute(query, {
                        "key": key,
                        "email": email,
                        "ip": ip,
                        "attempts": value.get("attempts") if isinstance(value.get("attempts"), list) else [],
                        "locked_until": value.get("locked_until") or None,
                    })
            connection.commit()

    def load_security_events(self):
        query = "SELECT event, email, ip, details, created_at FROM security_events ORDER BY created_at ASC"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [
                    {
                        "event": event or "",
                        "email": email or "",
                        "ip": ip or "",
                        "details": details or "",
                        "time": str(created_at or ""),
                    }
                    for event, email, ip, details, created_at in cursor.fetchall()
                ]

    def save_security_events(self, events):
        events = normalize_list(events)
        query = """
            INSERT INTO security_events (event, email, ip, details, created_at)
            VALUES (%(event)s, %(email)s, %(ip)s, %(details)s, COALESCE(%(created_at)s::timestamptz, now()))
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM security_events")
                for event in events:
                    if not isinstance(event, dict):
                        continue
                    cursor.execute(query, {
                        "event": event.get("event", ""),
                        "email": event.get("email", ""),
                        "ip": event.get("ip", ""),
                        "details": event.get("details", ""),
                        "created_at": event.get("time") or event.get("created_at") or None,
                    })
            connection.commit()


def split_attempt_key(key):
    parts = str(key or "").split("::", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return str(key or ""), ""


def get_security_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresSecurityRepository(client=client)
    return JsonSecurityRepository()
