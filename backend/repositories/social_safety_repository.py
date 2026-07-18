from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_BLOCKS_DATA = {"blocks": {}}
DEFAULT_REPORTS_DATA = {"reports": []}
DEFAULT_RESTRICTIONS_DATA = {"restrictions": {}}
DEFAULT_HIDDEN_STORIES_DATA = {"hidden_stories": {}}


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_relationship_map(data, key):
    if not isinstance(data, dict):
        return {key: {}}
    value = data.get(key) if key in data else data
    if not isinstance(value, dict):
        return {key: {}}

    normalized = {}
    for owner, targets in value.items():
        owner_email = normalize_email(owner)
        if not owner_email:
            continue
        if not isinstance(targets, list):
            targets = []
        clean_targets = []
        seen = set()
        for target in targets:
            target_email = normalize_email(target)
            if not target_email or target_email == owner_email or target_email in seen:
                continue
            seen.add(target_email)
            clean_targets.append(target_email)
        normalized[owner_email] = clean_targets
    return {key: normalized}


def normalize_reports_data(data):
    if not isinstance(data, dict) or not isinstance(data.get("reports"), list):
        return {"reports": []}

    reports = []
    for item in data["reports"]:
        if not isinstance(item, dict):
            continue
        reports.append({
            "id": str(item.get("id", "")),
            "reporter_email": normalize_email(item.get("reporter_email") or item.get("reporter")),
            "target_email": normalize_email(item.get("target_email") or item.get("target")),
            "reason": str(item.get("reason", "")),
            "details": str(item.get("details", "")),
            "status": str(item.get("status", "new") or "new"),
            "created_at": str(item.get("created_at", "")),
            "updated_at": str(item.get("updated_at", "")),
            "reviewed_by": normalize_email(item.get("reviewed_by")),
            "reviewed_at": str(item.get("reviewed_at", "")),
            "moderation_note": str(item.get("moderation_note", "")),
            "action": str(item.get("action", "")),
        })
    return {"reports": reports}


class JsonRelationshipMapRepository:
    def __init__(self, filename, key):
        self.key = key
        self.store = JsonStore(filename, {key: {}})

    def load_all(self):
        return normalize_relationship_map(self.store.load(), self.key)

    def save_all(self, data):
        self.store.save(normalize_relationship_map(data, self.key))


class JsonReportsRepository:
    def __init__(self, filename="reports.json"):
        self.store = JsonStore(filename, DEFAULT_REPORTS_DATA)

    def load_all(self):
        return normalize_reports_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_reports_data(data))


class PostgresRelationshipMapRepository:
    def __init__(self, table_name, owner_column, target_column, key, client=None):
        self.table_name = table_name
        self.owner_column = owner_column
        self.target_column = target_column
        self.key = key
        self.client = client or PostgresClient()

    def load_all(self):
        query = f"""
            SELECT owner.email, target.email
            FROM {self.table_name} item
            JOIN users owner ON owner.id = item.{self.owner_column}
            JOIN users target ON target.id = item.{self.target_column}
            ORDER BY owner.email ASC, item.created_at ASC
        """
        relationships = {}
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                for owner_email, target_email in cursor.fetchall():
                    owner = normalize_email(owner_email)
                    target = normalize_email(target_email)
                    if owner and target:
                        relationships.setdefault(owner, []).append(target)
        return {self.key: relationships}

    def save_all(self, data):
        data = normalize_relationship_map(data, self.key)
        insert_query = f"""
            INSERT INTO {self.table_name} ({self.owner_column}, {self.target_column})
            SELECT owner.id, target.id
            FROM users owner
            JOIN users target ON target.email = %(target)s
            WHERE owner.email = %(owner)s
            ON CONFLICT DO NOTHING
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {self.table_name}")
                for owner, targets in data[self.key].items():
                    for target in targets:
                        cursor.execute(insert_query, {"owner": owner, "target": target})
            connection.commit()


class PostgresReportsRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT reports.id, reporter.email, target.email, reports.reason,
                   reports.details, reports.status, reports.created_at, reports.updated_at,
                   reviewer.email, reports.reviewed_at, reports.moderation_note, reports.action
            FROM reports
            LEFT JOIN users reporter ON reporter.id = reports.reporter_id
            LEFT JOIN users target ON target.id = reports.target_user_id
            LEFT JOIN users reviewer ON reviewer.id = reports.reviewed_by_id
            ORDER BY reports.created_at ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                reports = []
                for row in cursor.fetchall():
                    reports.append({
                        "id": str(row[0]),
                        "reporter_email": normalize_email(row[1]),
                        "target_email": normalize_email(row[2]),
                        "reason": str(row[3] or ""),
                        "details": str(row[4] or ""),
                        "status": str(row[5] or "new"),
                        "created_at": str(row[6] or ""),
                        "updated_at": str(row[7] or ""),
                        "reviewed_by": normalize_email(row[8]),
                        "reviewed_at": str(row[9] or ""),
                        "moderation_note": str(row[10] or ""),
                        "action": str(row[11] or ""),
                    })
        return {"reports": reports}

    def save_all(self, data):
        data = normalize_reports_data(data)
        insert_query = """
            INSERT INTO reports (
                reporter_id, target_user_id, reason, details, status, created_at,
                updated_at, reviewed_by_id, reviewed_at, moderation_note, action
            )
            SELECT reporter.id, target.id, %(reason)s, %(details)s, %(status)s,
                   COALESCE(%(created_at)s::timestamptz, now()),
                   COALESCE(%(updated_at)s::timestamptz, now()),
                   reviewer.id,
                   %(reviewed_at)s::timestamptz,
                   %(moderation_note)s,
                   %(action)s
            FROM users reporter
            JOIN users target ON target.email = %(target_email)s
            LEFT JOIN users reviewer ON reviewer.email = %(reviewed_by)s
            WHERE reporter.email = %(reporter_email)s
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM reports")
                for report in data["reports"]:
                    if not report["reporter_email"] or not report["target_email"]:
                        continue
                    cursor.execute(insert_query, {
                        "reporter_email": report["reporter_email"],
                        "target_email": report["target_email"],
                        "reason": report["reason"],
                        "details": report["details"],
                        "status": report["status"],
                        "created_at": report["created_at"] or None,
                        "updated_at": report["updated_at"] or None,
                        "reviewed_by": report["reviewed_by"],
                        "reviewed_at": report["reviewed_at"] or None,
                        "moderation_note": report["moderation_note"],
                        "action": report["action"],
                    })
            connection.commit()


def get_blocks_repository(filename="blocks.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "blocks.json":
        return PostgresRelationshipMapRepository(
            "user_blocks", "blocker_id", "blocked_id", "blocks", client=client
        )
    return JsonRelationshipMapRepository(filename, "blocks")


def get_reports_repository(filename="reports.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "reports.json":
        return PostgresReportsRepository(client=client)
    return JsonReportsRepository(filename)


def get_restrictions_repository(filename="restrictions.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "restrictions.json":
        return PostgresRelationshipMapRepository(
            "user_restrictions", "restrictor_id", "restricted_id", "restrictions", client=client
        )
    return JsonRelationshipMapRepository(filename, "restrictions")


def get_hidden_stories_repository(filename="hidden_stories.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "hidden_stories.json":
        return PostgresRelationshipMapRepository(
            "hidden_story_authors", "viewer_id", "author_id", "hidden_stories", client=client
        )
    return JsonRelationshipMapRepository(filename, "hidden_stories")
