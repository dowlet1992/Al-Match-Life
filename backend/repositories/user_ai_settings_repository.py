from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_dict(data):
    return data if isinstance(data, dict) else {}


class JsonUserAiSettingsRepository:
    def __init__(
        self,
        settings_filename="database/user_ai_settings.json",
        legacy_privacy_filename="database/privacy_data.json",
    ):
        self.settings_store = JsonStore(settings_filename, {})
        self.legacy_privacy_store = JsonStore(legacy_privacy_filename, {})

    def load_all(self):
        return normalize_dict(self.settings_store.load())

    def load_legacy(self):
        return normalize_dict(self.legacy_privacy_store.load())

    def load_for_email(self, email):
        email = normalize_email(email)
        data = self.load_all()
        if email in data and isinstance(data.get(email), dict):
            return data[email]

        legacy_data = self.load_legacy()
        if isinstance(legacy_data.get(email), dict):
            return legacy_data[email]

        return {}

    def save_for_email(self, email, settings):
        email = normalize_email(email)
        if not email:
            return
        data = self.load_all()
        data[email] = settings if isinstance(settings, dict) else {}
        self.settings_store.save(data)


class PostgresUserAiSettingsRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT u.email, s.settings
            FROM user_ai_settings s
            JOIN users u ON u.id = s.user_id
            ORDER BY u.email ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return {
                    normalize_email(email): settings if isinstance(settings, dict) else {}
                    for email, settings in cursor.fetchall()
                }

    def load_for_email(self, email):
        email = normalize_email(email)
        query = """
            SELECT s.settings
            FROM user_ai_settings s
            JOIN users u ON u.id = s.user_id
            WHERE u.email = %(email)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"email": email})
                rows = cursor.fetchall()
                if not rows:
                    return {}
                settings = rows[0][0]
                return settings if isinstance(settings, dict) else {}

    def save_for_email(self, email, settings):
        email = normalize_email(email)
        if not email:
            return
        query = """
            INSERT INTO user_ai_settings (user_id, settings, updated_at)
            SELECT users.id, %(settings)s, now()
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT (user_id) DO UPDATE SET
                settings = EXCLUDED.settings,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {
                    "email": email,
                    "settings": settings if isinstance(settings, dict) else {},
                })
            connection.commit()


def get_user_ai_settings_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresUserAiSettingsRepository(client=client)
    return JsonUserAiSettingsRepository()
