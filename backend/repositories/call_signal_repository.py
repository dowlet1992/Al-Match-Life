from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


def normalize_dict(data):
    return data if isinstance(data, dict) else {}


class JsonCallSignalRepository:
    def __init__(self, filename="call_signals.json"):
        self.store = JsonStore(filename, {})

    def load_all(self):
        return normalize_dict(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_dict(data))


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


def get_call_signal_repository(filename="call_signals.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "call_signals.json":
        return PostgresCallSignalRepository(client=client)
    return JsonCallSignalRepository(filename)
