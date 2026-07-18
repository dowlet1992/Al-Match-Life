from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_FEED_DATA = {"posts": []}


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_feed_data(data):
    if not isinstance(data, dict):
        return {"posts": []}
    posts = data.get("posts")
    if not isinstance(posts, list):
        return {"posts": []}
    return {"posts": posts}


def normalize_post(post):
    if not isinstance(post, dict):
        return None

    normalized = dict(post)
    for key in ["likes", "saves", "comments", "shares", "hashtags", "media_items"]:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    normalized.setdefault("text", "")
    normalized.setdefault("type", "Идея")
    normalized.setdefault("language", "unknown")
    normalized.setdefault("location", "")
    return normalized


class JsonFeedRepository:
    def __init__(self, filename="database/feed_data.json"):
        self.store = JsonStore(filename, DEFAULT_FEED_DATA)

    def load_all(self):
        return normalize_feed_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_feed_data(data))


class PostgresFeedRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT p.id, author.email, author.name, p.type, p.text, p.language,
                           p.location, p.hashtags, p.media, p.created_at
                    FROM feed_posts p
                    JOIN users author ON author.id = p.author_id
                    ORDER BY p.created_at ASC
                """)
                posts = []
                post_index = {}
                for row in cursor.fetchall():
                    post = {
                        "id": str(row[0]),
                        "email": normalize_email(row[1]),
                        "author_email": normalize_email(row[1]),
                        "name": row[2] or "",
                        "author_name": row[2] or "",
                        "type": row[3] or "Идея",
                        "text": row[4] or "",
                        "language": row[5] or "unknown",
                        "location": row[6] or "",
                        "hashtags": row[7] if isinstance(row[7], list) else [],
                        "media_items": row[8] if isinstance(row[8], list) else [],
                        "created_at": str(row[9] or ""),
                        "date": str(row[9] or ""),
                        "likes": [],
                        "saves": [],
                        "comments": [],
                        "shares": [],
                    }
                    posts.append(post)
                    post_index[str(row[0])] = post

                cursor.execute("""
                    SELECT l.post_id, u.email
                    FROM feed_post_likes l
                    JOIN users u ON u.id = l.user_id
                    ORDER BY l.created_at ASC
                """)
                for post_id, email in cursor.fetchall():
                    post = post_index.get(str(post_id))
                    if post is not None:
                        post["likes"].append(normalize_email(email))

                cursor.execute("""
                    SELECT s.post_id, u.email
                    FROM feed_post_saves s
                    JOIN users u ON u.id = s.user_id
                    ORDER BY s.created_at ASC
                """)
                for post_id, email in cursor.fetchall():
                    post = post_index.get(str(post_id))
                    if post is not None:
                        post["saves"].append(normalize_email(email))

                cursor.execute("""
                    SELECT c.post_id, u.email, u.name, c.text, c.created_at
                    FROM feed_post_comments c
                    JOIN users u ON u.id = c.user_id
                    ORDER BY c.created_at ASC
                """)
                for post_id, email, name, text, created_at in cursor.fetchall():
                    post = post_index.get(str(post_id))
                    if post is not None:
                        post["comments"].append({
                            "author": normalize_email(email),
                            "author_name": name or "",
                            "text": text or "",
                            "date": str(created_at or ""),
                        })

        return {"posts": posts}

    def save_all(self, data):
        data = normalize_feed_data(data)
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM feed_post_comments")
                cursor.execute("DELETE FROM feed_post_saves")
                cursor.execute("DELETE FROM feed_post_likes")
                cursor.execute("DELETE FROM feed_posts")

                for raw_post in data["posts"]:
                    post = normalize_post(raw_post)
                    if post is None:
                        continue

                    post_id = str(post.get("id") or "").strip()
                    author = normalize_email(post.get("email") or post.get("author_email"))
                    if not post_id or not author:
                        continue

                    media = post.get("media_items", [])
                    if not media and post.get("media_url"):
                        media = [{
                            "url": post.get("media_url", ""),
                            "type": post.get("media_type", ""),
                            "name": post.get("media_name", ""),
                        }]

                    cursor.execute("""
                        INSERT INTO feed_posts (
                            id, author_id, type, text, language, location,
                            hashtags, media, created_at
                        )
                        SELECT %(id)s::uuid, users.id, %(type)s, %(text)s, %(language)s,
                               %(location)s, %(hashtags)s, %(media)s,
                               COALESCE(%(created_at)s::timestamptz, now())
                        FROM users
                        WHERE users.email = %(author_email)s
                        ON CONFLICT (id) DO UPDATE SET
                            type = EXCLUDED.type,
                            text = EXCLUDED.text,
                            language = EXCLUDED.language,
                            location = EXCLUDED.location,
                            hashtags = EXCLUDED.hashtags,
                            media = EXCLUDED.media,
                            updated_at = now()
                    """, {
                        "id": post_id,
                        "author_email": author,
                        "type": post.get("type", "Идея"),
                        "text": post.get("text", ""),
                        "language": post.get("language", "unknown"),
                        "location": post.get("location", ""),
                        "hashtags": post.get("hashtags", []),
                        "media": media,
                        "created_at": post.get("created_at") or post.get("date") or None,
                    })

                    for email in post["likes"]:
                        self._insert_user_post_link(cursor, "feed_post_likes", post_id, email)

                    for email in post["saves"]:
                        self._insert_user_post_link(cursor, "feed_post_saves", post_id, email)

                    for comment in post["comments"]:
                        if not isinstance(comment, dict):
                            continue
                        commenter = normalize_email(comment.get("author") or comment.get("email"))
                        if not commenter:
                            continue
                        cursor.execute("""
                            INSERT INTO feed_post_comments (post_id, user_id, text, created_at)
                            SELECT %(post_id)s::uuid, users.id, %(text)s,
                                   COALESCE(%(created_at)s::timestamptz, now())
                            FROM users
                            WHERE users.email = %(email)s
                        """, {
                            "post_id": post_id,
                            "email": commenter,
                            "text": comment.get("text", ""),
                            "created_at": comment.get("created_at") or comment.get("date") or None,
                        })

            connection.commit()

    def _insert_user_post_link(self, cursor, table_name, post_id, email):
        email = normalize_email(email)
        if not email:
            return
        cursor.execute(f"""
            INSERT INTO {table_name} (post_id, user_id)
            SELECT %(post_id)s::uuid, users.id
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT DO NOTHING
        """, {"post_id": post_id, "email": email})


def get_feed_repository(filename="database/feed_data.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "database/feed_data.json":
        return PostgresFeedRepository(client=client)
    return JsonFeedRepository(filename)
