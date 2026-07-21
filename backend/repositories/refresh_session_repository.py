from datetime import datetime, timezone
import hmac
import threading

from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


_JSON_REFRESH_LOCK = threading.RLock()


def utc_now_text():
    return datetime.now(timezone.utc).isoformat()


class JsonRefreshSessionRepository:
    def __init__(self, filename="auth_refresh_sessions.json"):
        self.store = JsonStore(filename, {})
        self._lock = _JSON_REFRESH_LOCK

    def _load(self):
        data = self.store.load()
        return data if isinstance(data, dict) else {}

    def create(self, session):
        with self._lock:
            data = self._load()
            data[str(session["token_id"])] = dict(session)
            self.store.save(data)

    def get(self, token_id):
        with self._lock:
            item = self._load().get(str(token_id))
        return dict(item) if isinstance(item, dict) else None

    def mark_rotated(self, token_id, replacement_token_id):
        with self._lock:
            data = self._load()
            item = data.get(str(token_id))
            if not isinstance(item, dict) or item.get("used_at") or item.get("revoked_at"):
                return False
            item["used_at"] = utc_now_text()
            item["replaced_by_token_id"] = str(replacement_token_id)
            self.store.save(data)
            return True

    def rotate(self, token_id, expected_token_hash, replacement):
        with self._lock:
            data = self._load()
            item = data.get(str(token_id))
            if not isinstance(item, dict) or not hmac.compare_digest(str(item.get("token_hash", "")), str(expected_token_hash)):
                return "invalid"
            family_id = item.get("family_id")
            if item.get("used_at") or item.get("revoked_at"):
                revoked_at = utc_now_text()
                for family_item in data.values():
                    if isinstance(family_item, dict) and family_item.get("family_id") == family_id:
                        family_item["revoked_at"] = family_item.get("revoked_at") or revoked_at
                self.store.save(data)
                return "reuse"
            item["used_at"] = utc_now_text()
            item["replaced_by_token_id"] = str(replacement["token_id"])
            data[str(replacement["token_id"])] = dict(replacement)
            self.store.save(data)
            return "rotated"

    def revoke_family(self, family_id):
        with self._lock:
            data = self._load()
            changed = False
            revoked_at = utc_now_text()
            for item in data.values():
                if isinstance(item, dict) and item.get("family_id") == family_id and not item.get("revoked_at"):
                    item["revoked_at"] = revoked_at
                    changed = True
            if changed:
                self.store.save(data)
            return changed


class PostgresRefreshSessionRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def create(self, session):
        query = """
            INSERT INTO auth_refresh_sessions (
                token_id, family_id, user_id, token_hash, device_id, session_version, issued_at, expires_at
            )
            SELECT %(token_id)s, %(family_id)s, users.id, %(token_hash)s, %(device_id)s,
                   %(session_version)s, to_timestamp(%(issued_at)s), to_timestamp(%(expires_at)s)
            FROM users WHERE users.email = %(email)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, session)
            connection.commit()

    def get(self, token_id):
        query = """
            SELECT s.token_id, s.family_id, u.email, s.token_hash, s.device_id,
                   s.session_version, extract(epoch from s.issued_at)::bigint,
                   extract(epoch from s.expires_at)::bigint, s.used_at, s.revoked_at,
                   s.replaced_by_token_id
            FROM auth_refresh_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_id = %(token_id)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"token_id": str(token_id)})
                row = cursor.fetchone()
        if not row:
            return None
        keys = ["token_id", "family_id", "email", "token_hash", "device_id", "session_version",
                "issued_at", "expires_at", "used_at", "revoked_at", "replaced_by_token_id"]
        return dict(zip(keys, row))

    def mark_rotated(self, token_id, replacement_token_id):
        query = """
            UPDATE auth_refresh_sessions
            SET used_at = now(), replaced_by_token_id = %(replacement)s
            WHERE token_id = %(token_id)s AND used_at IS NULL AND revoked_at IS NULL
            RETURNING token_id
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"token_id": str(token_id), "replacement": str(replacement_token_id)})
                changed = cursor.fetchone() is not None
            connection.commit()
        return changed

    def rotate(self, token_id, expected_token_hash, replacement):
        select_query = """
            SELECT family_id, token_hash, used_at, revoked_at
            FROM auth_refresh_sessions
            WHERE token_id = %(token_id)s
            FOR UPDATE
        """
        insert_query = """
            INSERT INTO auth_refresh_sessions (
                token_id, family_id, user_id, token_hash, device_id, session_version, issued_at, expires_at
            )
            SELECT %(token_id)s, %(family_id)s, users.id, %(token_hash)s, %(device_id)s,
                   %(session_version)s, to_timestamp(%(issued_at)s), to_timestamp(%(expires_at)s)
            FROM users WHERE users.email = %(email)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(select_query, {"token_id": str(token_id)})
                row = cursor.fetchone()
                if not row or not hmac.compare_digest(str(row[1] or ""), str(expected_token_hash)):
                    return "invalid"
                family_id, _token_hash, used_at, revoked_at = row
                if used_at is not None or revoked_at is not None:
                    cursor.execute(
                        "UPDATE auth_refresh_sessions SET revoked_at = COALESCE(revoked_at, now()) WHERE family_id = %(family_id)s",
                        {"family_id": family_id},
                    )
                    connection.commit()
                    return "reuse"
                cursor.execute(insert_query, replacement)
                cursor.execute(
                    "UPDATE auth_refresh_sessions SET used_at = now(), replaced_by_token_id = %(replacement)s WHERE token_id = %(token_id)s",
                    {"token_id": str(token_id), "replacement": str(replacement["token_id"])},
                )
            connection.commit()
        return "rotated"

    def revoke_family(self, family_id):
        query = """
            UPDATE auth_refresh_sessions SET revoked_at = COALESCE(revoked_at, now())
            WHERE family_id = %(family_id)s AND revoked_at IS NULL
            RETURNING token_id
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"family_id": str(family_id)})
                changed = cursor.fetchone() is not None
            connection.commit()
        return changed


def get_refresh_session_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresRefreshSessionRepository(client=client)
    return JsonRefreshSessionRepository()
