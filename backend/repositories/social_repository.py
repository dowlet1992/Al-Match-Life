from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_SOCIAL_DATA = {
    "friends": [],
    "follows": [],
    "friend_requests": [],
}


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_social_data(data):
    if not isinstance(data, dict):
        data = {}

    normalized = {}
    for key in DEFAULT_SOCIAL_DATA:
        normalized[key] = data.get(key) if isinstance(data.get(key), list) else []
    return normalized


class JsonSocialRepository:
    def __init__(self, filename="social.json"):
        self.store = JsonStore(filename, DEFAULT_SOCIAL_DATA)

    def load_all(self):
        return normalize_social_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_social_data(data))


class PostgresSocialRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT follower.email, following.email
                    FROM social_follows sf
                    JOIN users follower ON follower.id = sf.follower_id
                    JOIN users following ON following.id = sf.following_id
                    ORDER BY sf.created_at ASC
                """)
                follows = [
                    {"follower": normalize_email(row[0]), "following": normalize_email(row[1])}
                    for row in cursor.fetchall()
                ]

                cursor.execute("""
                    SELECT one.email, two.email
                    FROM friendships f
                    JOIN users one ON one.id = f.user_low_id
                    JOIN users two ON two.id = f.user_high_id
                    ORDER BY f.created_at ASC
                """)
                friends = [
                    {"user": normalize_email(row[0]), "friend": normalize_email(row[1])}
                    for row in cursor.fetchall()
                ]

                cursor.execute("""
                    SELECT sender.email, receiver.email
                    FROM friend_requests fr
                    JOIN users sender ON sender.id = fr.sender_id
                    JOIN users receiver ON receiver.id = fr.receiver_id
                    WHERE fr.status = 'pending'
                    ORDER BY fr.created_at ASC
                """)
                friend_requests = [
                    {"from": normalize_email(row[0]), "to": normalize_email(row[1])}
                    for row in cursor.fetchall()
                ]

        return {
            "friends": friends,
            "follows": follows,
            "friend_requests": friend_requests,
        }

    def save_all(self, data):
        data = normalize_social_data(data)
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM friend_requests WHERE status = 'pending'")
                cursor.execute("DELETE FROM friendships")
                cursor.execute("DELETE FROM social_follows")

                for item in data["follows"]:
                    follower = normalize_email(item.get("follower")) if isinstance(item, dict) else ""
                    following = normalize_email(item.get("following")) if isinstance(item, dict) else ""
                    if not follower or not following or follower == following:
                        continue
                    cursor.execute("""
                        INSERT INTO social_follows (follower_id, following_id)
                        SELECT follower.id, following.id
                        FROM users follower
                        JOIN users following ON following.email = %(following)s
                        WHERE follower.email = %(follower)s
                        ON CONFLICT DO NOTHING
                    """, {"follower": follower, "following": following})

                for item in data["friends"]:
                    user = normalize_email(item.get("user")) if isinstance(item, dict) else ""
                    friend = normalize_email(item.get("friend")) if isinstance(item, dict) else ""
                    if not user or not friend or user == friend:
                        continue
                    cursor.execute("""
                        WITH pair AS (
                            SELECT one.id AS one_id, two.id AS two_id
                            FROM users one
                            JOIN users two ON two.email = %(friend)s
                            WHERE one.email = %(user)s
                        )
                        INSERT INTO friendships (user_low_id, user_high_id)
                        SELECT
                            CASE WHEN one_id::text < two_id::text THEN one_id ELSE two_id END,
                            CASE WHEN one_id::text < two_id::text THEN two_id ELSE one_id END
                        FROM pair
                        ON CONFLICT DO NOTHING
                    """, {"user": user, "friend": friend})

                for item in data["friend_requests"]:
                    sender = normalize_email(item.get("from")) if isinstance(item, dict) else ""
                    receiver = normalize_email(item.get("to")) if isinstance(item, dict) else ""
                    if not sender or not receiver or sender == receiver:
                        continue
                    cursor.execute("""
                        INSERT INTO friend_requests (sender_id, receiver_id, status)
                        SELECT sender.id, receiver.id, 'pending'
                        FROM users sender
                        JOIN users receiver ON receiver.email = %(receiver)s
                        WHERE sender.email = %(sender)s
                        ON CONFLICT (sender_id, receiver_id) DO UPDATE SET
                            status = 'pending',
                            updated_at = now()
                    """, {"sender": sender, "receiver": receiver})

            connection.commit()


def get_social_repository(filename="social.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "social.json":
        return PostgresSocialRepository(client=client)
    return JsonSocialRepository(filename)
