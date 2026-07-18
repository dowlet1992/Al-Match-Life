import json

from scripts.export_json_to_postgres_sql import build_export, stable_uuid, user_id_for_email


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_postgres_sql_export_generates_transactional_sql(tmp_path):
    write_json(tmp_path / "users.json", [
        {
            "email": "alice@example.com",
            "password": "hashed",
            "name": "Alice",
            "languages": ["English"],
            "goals": ["Build"],
            "interests": ["AI"],
            "skills": ["Python"],
        },
        {"email": "bob@example.com", "password": "hashed", "name": "Bob"},
    ])
    write_json(tmp_path / "messages.json", [
        {"id": 1, "from": "alice@example.com", "to": "bob@example.com", "message": "Hello"}
    ])
    write_json(tmp_path / "social.json", {
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}],
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "friend_requests": [],
    })
    write_json(tmp_path / "database" / "feed_data.json", {
        "posts": [
            {
                "id": 10,
                "email": "alice@example.com",
                "text": "Post",
                "likes": ["bob@example.com"],
                "comments": [{"author": "bob@example.com", "text": "Nice"}],
                "saves": [],
            }
        ]
    })
    write_json(tmp_path / "notifications.json", {"notifications": []})
    write_json(tmp_path / "stories.json", {"stories": []})
    write_json(tmp_path / "reports.json", {"reports": [{
        "id": "report-1",
        "reporter_email": "alice@example.com",
        "target_email": "bob@example.com",
        "reason": "spam",
        "details": "Bad content",
        "status": "new",
        "created_at": "2026-01-01 10:00:00",
    }]})

    export = build_export(tmp_path)
    sql = export["sql"]

    assert export["ready"] is True
    assert export["errors"] == []
    assert sql.startswith("-- Generated JSON to PostgreSQL import")
    assert "BEGIN;" in sql
    assert sql.rstrip().endswith("COMMIT;")
    assert "INSERT INTO users" in sql
    assert "INSERT INTO messages" in sql
    assert "INSERT INTO feed_posts" in sql
    assert "INSERT INTO feed_post_likes" in sql
    assert "INSERT INTO reports" in sql
    assert user_id_for_email("alice@example.com") in sql
    assert stable_uuid("feed_post", 10) in sql


def test_postgres_sql_export_reports_plan_blockers(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "messages.json", [
        {"from": "alice@example.com", "to": "missing@example.com", "message": "Hello"}
    ])

    export = build_export(tmp_path)

    assert export["ready"] is False
    assert export["sql"] == ""
    assert export["errors"][0]["code"] == "missing_user_refs"
