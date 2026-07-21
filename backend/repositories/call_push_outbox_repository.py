from datetime import datetime, timezone

from backend.database import PostgresClient, load_database_settings


class PostgresCallPushOutboxRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def claim_due(self, now, batch_size=50):
        query = """
            WITH claimed AS (
                SELECT event_id FROM call_push_outbox
                WHERE status = 'pending' AND available_at <= %(now)s AND expires_at > %(now)s
                ORDER BY available_at, created_at FOR UPDATE SKIP LOCKED LIMIT %(batch_size)s
            )
            UPDATE call_push_outbox o SET status = 'processing', locked_at = %(now)s, attempts = attempts + 1
            FROM claimed WHERE o.event_id = claimed.event_id
            RETURNING o.event_id, o.room_id, o.event_type, o.payload, o.attempts, o.expires_at, o.target_user_id
        """
        params = {"now": datetime.fromtimestamp(float(now), tz=timezone.utc), "batch_size": min(max(int(batch_size), 1), 500)}
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE call_push_outbox SET status = 'expired' WHERE status IN ('pending','processing') AND expires_at <= %(now)s", params)
                cursor.execute("UPDATE call_push_outbox SET status = 'pending', locked_at = NULL WHERE status = 'processing' AND locked_at < %(now)s - interval '60 seconds'", params)
                cursor.execute(query, params)
                rows = cursor.fetchall()
            connection.commit()
        keys = ("event_id", "room_id", "event_type", "payload", "attempts", "expires_at", "target_user_id")
        return [dict(zip(keys, row)) for row in rows]

    def active_devices(self, target_user_id):
        query = "SELECT device_id, platform, token, token_hash FROM push_devices WHERE user_id = %(user_id)s AND revoked_at IS NULL"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"user_id": target_user_id})
                return [dict(zip(("device_id", "platform", "token", "token_hash"), row)) for row in cursor.fetchall()]

    def prepare_devices(self, event_id, target_user_id, now):
        insert_query = """
            INSERT INTO call_push_deliveries (event_id, device_id)
            SELECT %(event_id)s, id FROM push_devices
            WHERE user_id = %(user_id)s AND revoked_at IS NULL
            ON CONFLICT (event_id, device_id) DO NOTHING
        """
        select_query = """
            SELECT p.id, p.platform, p.token, p.token_hash, d.attempts
            FROM call_push_deliveries d JOIN push_devices p ON p.id = d.device_id
            WHERE d.event_id = %(event_id)s AND d.status = 'pending'
              AND d.available_at <= %(now)s AND p.revoked_at IS NULL
            ORDER BY p.id
        """
        params = {"event_id": event_id, "user_id": target_user_id, "now": datetime.fromtimestamp(float(now), tz=timezone.utc)}
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(insert_query, params)
                cursor.execute(select_query, params)
                rows = cursor.fetchall()
            connection.commit()
        return [dict(zip(("device_id", "platform", "token", "token_hash", "delivery_attempts"), row)) for row in rows]

    def finish_device(self, event_id, device_id, status, error_code="", available_at=None):
        query = """
            UPDATE call_push_deliveries SET status = %(status)s, attempts = attempts + 1,
                last_attempt_at = now(), last_error_code = %(error_code)s,
                available_at = COALESCE(%(available_at)s, available_at),
                delivered_at = CASE WHEN %(status)s = 'delivered' THEN now() ELSE delivered_at END
            WHERE event_id = %(event_id)s AND device_id = %(device_id)s AND status = 'pending'
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"event_id": event_id, "device_id": device_id, "status": status,
                                       "error_code": str(error_code)[:100], "available_at": available_at})
            connection.commit()

    def delivery_summary(self, event_id):
        query = """
            SELECT COUNT(*) FILTER (WHERE status = 'pending'),
                   COUNT(*) FILTER (WHERE status = 'delivered'),
                   COUNT(*) FILTER (WHERE status IN ('invalid_token','failed')),
                   MIN(available_at) FILTER (WHERE status = 'pending')
            FROM call_push_deliveries WHERE event_id = %(event_id)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"event_id": event_id})
                row = cursor.fetchone()
        row = row or (0, 0, 0, None)
        return {"pending": int(row[0] or 0), "delivered": int(row[1] or 0), "failed": int(row[2] or 0), "next_available_at": row[3]}

    def finish(self, event_id, status, error_code="", available_at=None):
        query = """
            UPDATE call_push_outbox SET status = %(status)s, last_error_code = %(error_code)s,
                available_at = COALESCE(%(available_at)s, available_at), locked_at = NULL,
                delivered_at = CASE WHEN %(status)s = 'delivered' THEN now() ELSE delivered_at END
            WHERE event_id = %(event_id)s AND status = 'processing'
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"event_id": event_id, "status": status, "error_code": str(error_code)[:100], "available_at": available_at})
            connection.commit()

    def revoke_token(self, token_hash):
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE push_devices SET revoked_at = now() WHERE token_hash = %(token_hash)s AND revoked_at IS NULL", {"token_hash": token_hash})
            connection.commit()

    def dry_run_count(self, now):
        query = "SELECT COUNT(*) FROM call_push_outbox WHERE status = 'pending' AND available_at <= %(now)s AND expires_at > %(now)s"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, {"now": datetime.fromtimestamp(float(now), tz=timezone.utc)})
                row = cursor.fetchone()
        return int(row[0]) if row else 0


def get_call_push_outbox_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if not settings.postgres_enabled:
        return None
    return PostgresCallPushOutboxRepository(client)
