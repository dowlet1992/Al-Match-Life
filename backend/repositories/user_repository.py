from backend.database import PostgresClient, load_database_settings
from backend.models import User
from backend.repositories.json_store import JsonStore


USER_COLUMNS = [
    "name",
    "age",
    "email",
    "password_hash",
    "country",
    "bio",
    "profession",
    "looking_for",
    "languages",
    "goals",
    "interests",
    "skills",
    "trust_score",
    "verified",
    "profile_completed",
    "created_at",
    "onboarding_completed",
    "onboarding_skipped",
    "account_verified",
    "account_verified_at",
    "account_verified_via",
]


def user_from_record(record):
    if record is None:
        return None

    if isinstance(record, dict):
        values = record
    else:
        values = dict(zip(USER_COLUMNS, record))

    return User(
        values.get("name"),
        values.get("age"),
        values.get("email"),
        values.get("password") or values.get("password_hash"),
        values.get("country"),
        values.get("bio"),
        values.get("profession", ""),
        values.get("looking_for", ""),
        values.get("languages", []),
        values.get("goals", []),
        values.get("interests", []),
        values.get("skills", []),
        values.get("trust_score", 50),
        values.get("verified", False),
        values.get("profile_completed", False),
        values.get("created_at"),
        values.get("onboarding_completed", False),
        values.get("onboarding_skipped", False),
        values.get("account_verified", True),
        values.get("account_verified_at", ""),
        values.get("account_verified_via", ""),
    )


def user_to_json_record(user):
    return user.info()


def user_to_database_params(user):
    return {
        "email": str(user.email or "").strip().lower(),
        "password_hash": user.password,
        "name": user.name,
        "age": user.age,
        "country": user.country,
        "bio": user.bio,
        "profession": user.profession,
        "looking_for": user.looking_for,
        "languages": user.languages if isinstance(user.languages, list) else [],
        "goals": user.goals if isinstance(user.goals, list) else [],
        "interests": user.interests if isinstance(user.interests, list) else [],
        "skills": user.skills if isinstance(user.skills, list) else [],
        "trust_score": user.trust_score,
        "verified": user.verified,
        "profile_completed": user.profile_completed,
        "created_at": user.created_at,
        "onboarding_completed": user.onboarding_completed,
        "onboarding_skipped": user.onboarding_skipped,
        "account_verified": user.account_verified,
        "account_verified_at": user.account_verified_at or None,
        "account_verified_via": user.account_verified_via,
    }


class JsonUserRepository:
    def __init__(self, filename="users.json"):
        self.store = JsonStore(filename, [])

    def load_all(self):
        data = self.store.load()
        if not isinstance(data, list):
            return None

        users = []
        for item in data:
            if isinstance(item, dict):
                users.append(user_from_record(item))
        return users

    def save_all(self, users):
        users = list(users or [])
        self.store.save([user_to_json_record(user) for user in users])


class PostgresUserRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT name, age, email, password_hash, country, bio, profession, looking_for,
                   languages, goals, interests, skills, trust_score, verified,
                   profile_completed, created_at, onboarding_completed, onboarding_skipped,
                   account_verified, account_verified_at, account_verified_via
            FROM users
            ORDER BY created_at ASC, email ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return [user_from_record(row) for row in cursor.fetchall()]

    def save_all(self, users):
        query = """
            INSERT INTO users (
                email, password_hash, name, age, country, bio, profession, looking_for,
                languages, goals, interests, skills, trust_score, verified,
                profile_completed, created_at, onboarding_completed, onboarding_skipped,
                account_verified, account_verified_at, account_verified_via
            )
            VALUES (
                %(email)s, %(password_hash)s, %(name)s, %(age)s, %(country)s, %(bio)s,
                %(profession)s, %(looking_for)s, %(languages)s, %(goals)s, %(interests)s,
                %(skills)s, %(trust_score)s, %(verified)s, %(profile_completed)s,
                %(created_at)s, %(onboarding_completed)s, %(onboarding_skipped)s,
                %(account_verified)s, %(account_verified_at)s, %(account_verified_via)s
            )
            ON CONFLICT (email) DO UPDATE SET
                password_hash = EXCLUDED.password_hash,
                name = EXCLUDED.name,
                age = EXCLUDED.age,
                country = EXCLUDED.country,
                bio = EXCLUDED.bio,
                profession = EXCLUDED.profession,
                looking_for = EXCLUDED.looking_for,
                languages = EXCLUDED.languages,
                goals = EXCLUDED.goals,
                interests = EXCLUDED.interests,
                skills = EXCLUDED.skills,
                trust_score = EXCLUDED.trust_score,
                verified = EXCLUDED.verified,
                profile_completed = EXCLUDED.profile_completed,
                onboarding_completed = EXCLUDED.onboarding_completed,
                onboarding_skipped = EXCLUDED.onboarding_skipped,
                account_verified = EXCLUDED.account_verified,
                account_verified_at = EXCLUDED.account_verified_at,
                account_verified_via = EXCLUDED.account_verified_via,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                for user in users:
                    cursor.execute(query, user_to_database_params(user))
                active_emails = [
                    str(user.email or "").strip().lower()
                    for user in users
                    if str(user.email or "").strip()
                ]
                cursor.execute(
                    "DELETE FROM users WHERE NOT (email = ANY(%(active_emails)s))",
                    {"active_emails": active_emails},
                )
            connection.commit()


def get_user_repository(filename="users.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "users.json":
        return PostgresUserRepository(client=client)
    return JsonUserRepository(filename)
