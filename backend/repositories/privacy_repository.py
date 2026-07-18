from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_PRIVACY_DATA = {"users": {}}


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_privacy_data(data):
    if not isinstance(data, dict):
        return {"users": {}}
    if "users" in data:
        return {"users": data.get("users") if isinstance(data.get("users"), dict) else {}}
    return {"users": data}


class JsonPrivacyRepository:
    def __init__(self, filename="database/privacy_data.json"):
        self.store = JsonStore(filename, DEFAULT_PRIVACY_DATA)

    def load_all(self):
        return normalize_privacy_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_privacy_data(data))


class PostgresPrivacyRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT u.email, p.receive_recommendations, p.show_me_to_others,
                   p.show_in_search, p.allow_messages, p.verified_only_messages,
                   p.vip_mode
            FROM privacy_settings p
            JOIN users u ON u.id = p.user_id
            ORDER BY u.email ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                users = {}
                for row in cursor.fetchall():
                    email = normalize_email(row[0])
                    users[email] = {
                        "receive_recommendations": row[1] is True,
                        "show_me_to_others": row[2] is True,
                        "show_in_search": row[3] is True,
                        "allow_messages": row[4] is True,
                        "verified_only_messages": row[5] is True,
                        "vip_mode": row[6] is True,
                    }
        return {"users": users}

    def save_all(self, data):
        data = normalize_privacy_data(data)
        query = """
            INSERT INTO privacy_settings (
                user_id, receive_recommendations, show_me_to_others, show_in_search,
                allow_messages, verified_only_messages, vip_mode, updated_at
            )
            SELECT users.id, %(receive_recommendations)s, %(show_me_to_others)s,
                   %(show_in_search)s, %(allow_messages)s, %(verified_only_messages)s,
                   %(vip_mode)s, now()
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT (user_id) DO UPDATE SET
                receive_recommendations = EXCLUDED.receive_recommendations,
                show_me_to_others = EXCLUDED.show_me_to_others,
                show_in_search = EXCLUDED.show_in_search,
                allow_messages = EXCLUDED.allow_messages,
                verified_only_messages = EXCLUDED.verified_only_messages,
                vip_mode = EXCLUDED.vip_mode,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                for email, settings in data["users"].items():
                    if not isinstance(settings, dict):
                        continue
                    cursor.execute(query, {
                        "email": normalize_email(email),
                        "receive_recommendations": settings.get("receive_recommendations", True) is True,
                        "show_me_to_others": settings.get("show_me_to_others", True) is True,
                        "show_in_search": settings.get("show_in_search", True) is True,
                        "allow_messages": settings.get("allow_messages", True) is True,
                        "verified_only_messages": settings.get("verified_only_messages", False) is True,
                        "vip_mode": settings.get("vip_mode", False) is True,
                    })
            connection.commit()


def get_privacy_repository(filename="database/privacy_data.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "database/privacy_data.json":
        return PostgresPrivacyRepository(client=client)
    return JsonPrivacyRepository(filename)
