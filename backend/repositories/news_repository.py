import uuid

from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "ai-match-life-news")


def normalize_list(data):
    return data if isinstance(data, list) else []


def normalize_email(value):
    return str(value or "").strip().lower()


def news_database_id(item):
    raw_id = str(item.get("id") or "").strip()
    try:
        return str(uuid.UUID(raw_id))
    except (ValueError, TypeError):
        key = raw_id or "|".join([
            str(item.get("created_at") or ""),
            str(item.get("title") or ""),
            str(item.get("body") or ""),
        ])
        return str(uuid.uuid5(UUID_NAMESPACE, key))


class JsonNewsRepository:
    def __init__(self, filename="news.json"):
        self.store = JsonStore(filename, [])

    def load_all(self):
        return normalize_list(self.store.load())

    def save_all(self, news_items, limit=500):
        self.store.save(normalize_list(news_items)[-limit:])


class PostgresNewsRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT n.id, author.email, n.author_name, n.title, n.body, n.source,
                   n.location, n.media, n.created_at
            FROM news_items n
            LEFT JOIN users author ON author.id = n.author_id
            ORDER BY n.created_at ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [
                    {
                        "id": str(news_id),
                        "author_email": normalize_email(author_email),
                        "author_name": author_name or "AI Match Life",
                        "title": title or "",
                        "body": body or "",
                        "source": source or "",
                        "location": location or "",
                        "media": media if isinstance(media, list) else [],
                        "created_at": str(created_at or ""),
                    }
                    for news_id, author_email, author_name, title, body, source, location, media, created_at
                    in cursor.fetchall()
                ]

    def save_all(self, news_items, limit=500):
        query = """
            INSERT INTO news_items (
                id, author_id, author_name, title, body, source, location, media, created_at
            )
            SELECT %(id)s::uuid, users.id, %(author_name)s, %(title)s, %(body)s,
                   %(source)s, %(location)s, %(media)s,
                   COALESCE(%(created_at)s::timestamptz, now())
            FROM (SELECT 1) seed
            LEFT JOIN users ON users.email = %(author_email)s
            ON CONFLICT (id) DO UPDATE SET
                author_name = EXCLUDED.author_name,
                title = EXCLUDED.title,
                body = EXCLUDED.body,
                source = EXCLUDED.source,
                location = EXCLUDED.location,
                media = EXCLUDED.media
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM news_items")
                for item in normalize_list(news_items)[-limit:]:
                    if not isinstance(item, dict):
                        continue
                    cursor.execute(query, {
                        "id": news_database_id(item),
                        "author_email": normalize_email(item.get("author_email") or item.get("email")),
                        "author_name": item.get("author_name", "AI Match Life"),
                        "title": item.get("title", ""),
                        "body": item.get("body", ""),
                        "source": item.get("source", ""),
                        "location": item.get("location", ""),
                        "media": item.get("media") if isinstance(item.get("media"), list) else [],
                        "created_at": item.get("created_at") or None,
                    })
            connection.commit()


def get_news_repository(filename="news.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "news.json":
        return PostgresNewsRepository(client=client)
    return JsonNewsRepository(filename)
