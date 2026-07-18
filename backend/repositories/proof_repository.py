import uuid

from backend.database import PostgresClient, load_database_settings
from backend.repositories.json_store import JsonStore


DEFAULT_PROOF_DATA = {"proofs": []}
UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "ai-match-life-proof")


def normalize_email(value):
    return str(value or "").strip().lower()


def normalize_proof_data(data):
    if not isinstance(data, dict) or not isinstance(data.get("proofs"), list):
        return {"proofs": []}
    return {"proofs": data["proofs"]}


def proof_database_id(proof):
    raw_id = str(proof.get("id") or "").strip()
    try:
        return str(uuid.UUID(raw_id))
    except (ValueError, TypeError):
        key = raw_id or "|".join([
            normalize_email(proof.get("email") or proof.get("user_email")),
            str(proof.get("created_at") or ""),
            str(proof.get("title") or proof.get("type") or ""),
        ])
        return str(uuid.uuid5(UUID_NAMESPACE, key))


class JsonProofRepository:
    def __init__(self, filename="database/proof_data.json"):
        self.store = JsonStore(filename, DEFAULT_PROOF_DATA)

    def load_all(self):
        return normalize_proof_data(self.store.load())

    def save_all(self, data):
        self.store.save(normalize_proof_data(data))


class PostgresProofRepository:
    def __init__(self, client=None):
        self.client = client or PostgresClient()

    def load_all(self):
        query = """
            SELECT p.id, u.email, p.type, p.title, p.description, p.media_url,
                   p.status, p.ai_summary, p.created_at
            FROM proof_items p
            JOIN users u ON u.id = p.user_id
            ORDER BY p.created_at ASC
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                proofs = []
                for row in cursor.fetchall():
                    proof_id, email, type_value, title, description, media_url, status, ai_summary, created_at = row
                    proofs.append({
                        "id": str(proof_id),
                        "email": normalize_email(email),
                        "type": type_value or "",
                        "title": title or "",
                        "description": description or "",
                        "media_url": media_url or "",
                        "status": status or "new",
                        "ai_summary": ai_summary or "",
                        "created_at": str(created_at or ""),
                    })
        return {"proofs": proofs}

    def save_all(self, data):
        data = normalize_proof_data(data)
        query = """
            INSERT INTO proof_items (
                id, user_id, type, title, description, media_url, status, ai_summary, created_at
            )
            SELECT %(id)s::uuid, users.id, %(type)s, %(title)s, %(description)s,
                   %(media_url)s, %(status)s, %(ai_summary)s,
                   COALESCE(%(created_at)s::timestamptz, now())
            FROM users
            WHERE users.email = %(email)s
            ON CONFLICT (id) DO UPDATE SET
                type = EXCLUDED.type,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                media_url = EXCLUDED.media_url,
                status = EXCLUDED.status,
                ai_summary = EXCLUDED.ai_summary,
                updated_at = now()
        """
        with self.client.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM proof_items")
                for proof in data["proofs"]:
                    if not isinstance(proof, dict):
                        continue
                    email = normalize_email(proof.get("email") or proof.get("user_email"))
                    if not email:
                        continue
                    cursor.execute(query, {
                        "id": proof_database_id(proof),
                        "email": email,
                        "type": proof.get("type", ""),
                        "title": proof.get("title", ""),
                        "description": proof.get("description", ""),
                        "media_url": proof.get("media_url", ""),
                        "status": proof.get("status", "new"),
                        "ai_summary": proof.get("ai_summary", ""),
                        "created_at": proof.get("created_at") or None,
                    })
            connection.commit()


def get_proof_repository(filename="database/proof_data.json", settings=None, client=None):
    settings = settings or load_database_settings()
    if settings.postgres_enabled and filename == "database/proof_data.json":
        return PostgresProofRepository(client=client)
    return JsonProofRepository(filename)
