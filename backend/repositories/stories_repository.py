import uuid

from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_STORIES_DATA = {"stories": []}
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "ai-match-life-stories")


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_stories_data(data):
    if not isinstance(data, dict) or not isinstance(data.get("stories"), list):
        return {"stories": []}
    return {"stories": data["stories"]}


def story_database_id(story):
    raw_id = str(story.get("id") or "").strip()
    try:
        return str(uuid.UUID(raw_id))
    except (ValueError, TypeError):
        key = raw_id or "|".join([
            normalize_email(story.get("email") or story.get("author_email")),
            str(story.get("created_at") or ""),
            str(story.get("media_url") or ""),
        ])
        return str(uuid.uuid5(UUID_NAMESPACE, key))


class JsonStoriesRepository:
    def __init__(self, filename="stories.json"):
        self.store = JsonStore(filename, DEFAULT_STORIES_DATA)

    def load_all(self):
        return normalize_stories_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_stories_data(data))


class PostgresStoriesRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT s.id, u.email, u.name, s.media_url, s.media_type, s.text, s.created_at
            FROM stories s
            JOIN users u ON u.id = s.author_id
            WHERE s.expires_at > now()
            ORDER BY s.created_at ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                stories = []
                for row in cursor.fetchall():
                    story_id, email, name, media_url, media_type, text, created_at = row
                    stories.append({
                        "id": str(story_id),
                        "email": normalize_email(email),
                        "name": name or "",
                        "media_url": media_url or "",
                        "media_type": media_type or "",
                        "text": text or "",
                        "created_at": str(created_at or ""),
                        "views": [],
                        "viewers": [],
                    })
        return {"stories": stories}

    def save_all(self, data):
        data = normalize_stories_data(data)
        query = """
            INSERT INTO stories (id, author_id, media_url, media_type, text, created_at, expires_at)
            SELECT %(id)s::uuid, users.id, %(media_url)s, %(media_type)s, %(text)s,
                   COALESCE(%(created_at)s::timestamptz, now()),
                   COALESCE(%(expires_at)s::timestamptz, now() + interval '24 hours')
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT (id) DO UPDATE SET
                media_url = EXCLUDED.media_url,
                media_type = EXCLUDED.media_type,
                text = EXCLUDED.text
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM stories")
                for story in data["stories"]:
                    if not isinstance(story, dict):
                        continue
                    email = normalize_email(story.get("email") or story.get("author_email"))
                    if not email:
                        continue
                    expires_at = story.get("expires_at")
                    cursor.execute(query, {
                        "id": story_database_id(story),
                        "email": email,
                        "media_url": story.get("media_url", ""),
                        "media_type": story.get("media_type", ""),
                        "text": story.get("text", ""),
                        "created_at": story.get("created_at") or None,
                        "expires_at": expires_at,
                    })
            connection.commit()


def get_stories_repository(filename="stories.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "stories.json":
        return PostgresStoriesRepository(client=client)
    return JsonStoriesRepository(filename)
