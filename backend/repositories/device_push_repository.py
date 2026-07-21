import threading
from datetime import datetime, timezone

from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


_JSON_PUSH_LOCK = threading.RLock()


def normalize_email(value):
    return str(value or "").strip().lower()


class JsonDevicePushRepository:
    def __init__(self, filename="push_devices.json"):
        self.store = JsonStore(filename, {"devices": []})

    def upsert(self, email, registration):
        email = normalize_email(email)
        now = datetime.now(timezone.utc).isoformat()
        with _JSON_PUSH_LOCK:
            data = self.store.load()
            devices = data.get("devices", []) if isinstance(data, dict) else []
            devices = [item for item in devices if isinstance(item, dict) and not (
                item.get("token_hash") == registration["token_hash"]
                or (normalize_email(item.get("email")) == email and item.get("device_id") == registration["device_id"])
            )]
            devices.append({**registration, "email": email, "last_seen_at": now})
            self.store.save({"devices": devices})
        return {**registration, "last_seen_at": now}

    def list_for_user(self, email):
        email = normalize_email(email)
        with _JSON_PUSH_LOCK:
            data = self.store.load()
            return [dict(item) for item in data.get("devices", []) if isinstance(item, dict) and normalize_email(item.get("email")) == email]

    def revoke(self, email, device_id):
        email = normalize_email(email)
        with _JSON_PUSH_LOCK:
            data = self.store.load()
            devices = data.get("devices", []) if isinstance(data, dict) else []
            kept = [item for item in devices if not (isinstance(item, dict) and normalize_email(item.get("email")) == email and item.get("device_id") == device_id)]
            if len(kept) == len(devices):
                return False
            self.store.save({"devices": kept})
            return True

    def revoke_all(self, email):
        email = normalize_email(email)
        with _JSON_PUSH_LOCK:
            data = self.store.load()
            devices = data.get("devices", []) if isinstance(data, dict) else []
            kept = [item for item in devices if not (isinstance(item, dict) and normalize_email(item.get("email")) == email)]
            if len(kept) != len(devices):
                self.store.save({"devices": kept})
            return len(devices) - len(kept)


class PostgresDevicePushRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def upsert(self, email, registration):
        query = """
            INSERT INTO push_devices (user_id, device_id, platform, token, token_hash, app_version, locale)
            SELECT id, %(device_id)s, %(platform)s, %(token)s, %(token_hash)s, %(app_version)s, %(locale)s
            FROM users WHERE email = %(email)s
            ON CONFLICT (user_id, device_id) DO UPDATE SET
                platform = EXCLUDED.platform, token = EXCLUDED.token, token_hash = EXCLUDED.token_hash,
                app_version = EXCLUDED.app_version, locale = EXCLUDED.locale,
                last_seen_at = now(), revoked_at = NULL
            RETURNING device_id, platform, app_version, locale, last_seen_at
        """
        params = {**registration, "email": normalize_email(email)}
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM push_devices WHERE token_hash = %(token_hash)s "
                    "AND NOT (user_id = (SELECT id FROM users WHERE email = %(email)s) AND device_id = %(device_id)s)",
                    params,
                )
                cursor.execute(query, params)
                row = cursor.fetchone()
            connection.commit()
        if not row:
            raise LookupError("Push device owner not found")
        return dict(zip(("device_id", "platform", "app_version", "locale", "last_seen_at"), row))

    def list_for_user(self, email):
        query = """
            SELECT d.device_id, d.platform, d.app_version, d.locale, d.last_seen_at
            FROM push_devices d JOIN users u ON u.id = d.user_id
            WHERE u.email = %(email)s AND d.revoked_at IS NULL ORDER BY d.last_seen_at DESC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"email": normalize_email(email)})
                return [dict(zip(("device_id", "platform", "app_version", "locale", "last_seen_at"), row)) for row in cursor.fetchall()]

    def revoke(self, email, device_id):
        query = """
            UPDATE push_devices d SET revoked_at = now()
            FROM users u WHERE d.user_id = u.id AND u.email = %(email)s
              AND d.device_id = %(device_id)s AND d.revoked_at IS NULL
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"email": normalize_email(email), "device_id": str(device_id)})
                changed = int(getattr(cursor, "rowcount", 0) or 0) > 0
            connection.commit()
        return changed

    def revoke_all(self, email):
        query = """
            UPDATE push_devices d SET revoked_at = now()
            FROM users u WHERE d.user_id = u.id AND u.email = %(email)s AND d.revoked_at IS NULL
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"email": normalize_email(email)})
                changed = int(getattr(cursor, "rowcount", 0) or 0)
            connection.commit()
        return max(changed, 0)


def get_device_push_repository(settings=None, client=None, filename="push_devices.json"):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresDevicePushRepository(client=client)
    return JsonDevicePushRepository(filename)
