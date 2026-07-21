from backend.database import PostgresClient, load_database_settings


class PostgresRateLimitRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def allow(self, key_hash, category, limit, window_seconds, now):
        window_seconds = max(int(window_seconds), 1)
        bucket_start = int(float(now)) // window_seconds * window_seconds
        query = """
            WITH expired AS (
                DELETE FROM rate_limit_buckets WHERE expires_at < now()
            ), upserted AS (
                INSERT INTO rate_limit_buckets (
                    key_hash, category, bucket_start, request_count, expires_at
                ) VALUES (
                    %(key_hash)s, %(category)s, %(bucket_start)s, 1,
                    to_timestamp(%(expires_epoch)s)
                )
                ON CONFLICT (key_hash, category, bucket_start) DO UPDATE SET
                    request_count = rate_limit_buckets.request_count + 1,
                    expires_at = GREATEST(rate_limit_buckets.expires_at, EXCLUDED.expires_at)
                RETURNING request_count
            )
            SELECT request_count FROM upserted
        """
        params = {
            "key_hash": str(key_hash),
            "category": str(category),
            "bucket_start": bucket_start,
            "expires_epoch": bucket_start + (window_seconds * 2),
        }
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
            connection.commit()
        count = int(row[0]) if row else max(int(limit), 1) + 1
        return count <= max(int(limit), 1)

    def cleanup_expired(self):
        query = "DELETE FROM rate_limit_buckets WHERE expires_at < now()"
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                deleted_count = getattr(cursor, "rowcount", 0)
            connection.commit()
        return max(int(deleted_count or 0), 0)


def get_rate_limit_repository(settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled:
        return PostgresRateLimitRepository(client=client)
    return None
