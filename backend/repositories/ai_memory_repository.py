from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_dict(data):
    return data if isinstance(data, dict) else {}


class JsonAiMemoryRepository:
    def __init__(self, core_filename="ai_core_memory.json", feed_filename="ai_feed_learning.json"):
        self.core_store = JsonStore(core_filename, {})
        self.feed_store = JsonStore(feed_filename, {})

    def load_core_memory(self):
        return normalize_dict(self.core_store.load())

    def save_core_memory(self, data):
        self.core_store.save(normalize_dict(data))

    def load_feed_learning(self):
        return normalize_dict(self.feed_store.load())

    def save_feed_learning(self, data):
        self.feed_store.save(normalize_dict(data))


class PostgresAiMemoryRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_core_memory(self):
        query = """
            SELECT u.email, m.mode, m.question, m.answer, m.created_at
            FROM ai_core_memory m
            JOIN users u ON u.id = m.user_id
            ORDER BY u.email ASC, m.created_at ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                data = {}
                for email, mode, question, answer, created_at in cursor.fetchall():
                    key = normalize_email(email)
                    data.setdefault(key, []).append({
                        "time": str(created_at or ""),
                        "mode": mode or "",
                        "question": question or "",
                        "answer": answer or "",
                    })
        return data

    def save_core_memory(self, data):
        data = normalize_dict(data)
        query = """
            INSERT INTO ai_core_memory (user_id, mode, question, answer, created_at)
            SELECT users.id, %(mode)s, %(question)s, %(answer)s,
                   COALESCE(%(created_at)s::timestamptz, now())
            FROM users
            WHERE users.email = %(email)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM ai_core_memory")
                for email, items in data.items():
                    email = normalize_email(email)
                    if not isinstance(items, list) or not email:
                        continue
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        cursor.execute(query, {
                            "email": email,
                            "mode": item.get("mode", ""),
                            "question": item.get("question", ""),
                            "answer": item.get("answer", ""),
                            "created_at": item.get("time") or item.get("created_at") or None,
                        })
            connection.commit()

    def load_feed_learning(self):
        query = """
            SELECT u.email, l.languages, l.types, l.hashtags, l.locations, l.actions, l.updated_at
            FROM ai_feed_learning l
            JOIN users u ON u.id = l.user_id
            ORDER BY u.email ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                data = {}
                for email, languages, types, hashtags, locations, actions, updated_at in cursor.fetchall():
                    data[normalize_email(email)] = {
                        "languages": languages if isinstance(languages, dict) else {},
                        "types": types if isinstance(types, dict) else {},
                        "hashtags": hashtags if isinstance(hashtags, dict) else {},
                        "locations": locations if isinstance(locations, dict) else {},
                        "actions": actions if isinstance(actions, list) else [],
                        "updated_at": str(updated_at or ""),
                    }
        return data

    def save_feed_learning(self, data):
        data = normalize_dict(data)
        query = """
            INSERT INTO ai_feed_learning (
                user_id, languages, types, hashtags, locations, actions, updated_at
            )
            SELECT users.id, %(languages)s, %(types)s, %(hashtags)s, %(locations)s,
                   %(actions)s, COALESCE(%(updated_at)s::timestamptz, now())
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT (user_id) DO UPDATE SET
                languages = EXCLUDED.languages,
                types = EXCLUDED.types,
                hashtags = EXCLUDED.hashtags,
                locations = EXCLUDED.locations,
                actions = EXCLUDED.actions,
                updated_at = EXCLUDED.updated_at
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                for email, item in data.items():
                    email = normalize_email(email)
                    if not email or not isinstance(item, dict):
                        continue
                    cursor.execute(query, {
                        "email": email,
                        "languages": item.get("languages") if isinstance(item.get("languages"), dict) else {},
                        "types": item.get("types") if isinstance(item.get("types"), dict) else {},
                        "hashtags": item.get("hashtags") if isinstance(item.get("hashtags"), dict) else {},
                        "locations": item.get("locations") if isinstance(item.get("locations"), dict) else {},
                        "actions": item.get("actions") if isinstance(item.get("actions"), list) else [],
                        "updated_at": item.get("updated_at") or None,
                    })
            connection.commit()


def get_ai_memory_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresAiMemoryRepository(client=client)
    return JsonAiMemoryRepository()
