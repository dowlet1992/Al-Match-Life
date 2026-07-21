import json

from scripts.export_json_to_postgres_sql import build_export, user_id_for_email


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
    write_json(tmp_path / "database" / "privacy_data.json", {"users": {
        "alice@example.com": {"show_in_search": False, "vip_mode": True}
    }})
    write_json(tmp_path / "database" / "proof_data.json", {"proofs": [{
        "email": "alice@example.com", "title": "Verified company", "type": "business"
    }]})
    write_json(tmp_path / "verification_codes.json", {"verify:alice": {
        "code": "123456", "purpose": "account_verify", "contact_type": "email",
        "contact_value": "alice@example.com", "expires_at": "2026-01-01 10:10:00"
    }})
    write_json(tmp_path / "login_attempts.json", {"alice@example.com::127.0.0.1": {"attempts": []}})
    write_json(tmp_path / "presence_status.json", {"alice@example.com": 1767225600})
    write_json(tmp_path / "typing_status.json", {"alice@example.com->bob@example.com": 1767225600})
    write_json(tmp_path / "call_signals.json", {"alice__bob__audio": {"messages": [
        {"from": "alice@example.com", "to": "bob@example.com"}
    ]}})

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
    assert "INSERT INTO privacy_settings" in sql
    assert "INSERT INTO proof_items" in sql
    assert "INSERT INTO verification_codes" in sql
    assert "INSERT INTO login_attempts" in sql
    assert "INSERT INTO realtime_presence" in sql
    assert "INSERT INTO realtime_typing" in sql
    assert "INSERT INTO call_signals" in sql
    assert "123456" not in sql
    assert user_id_for_email("alice@example.com") in sql
    assert "INSERT INTO feed_posts" in sql
    assert "VALUES (10," in sql


def test_postgres_sql_export_reports_plan_blockers(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "messages.json", [
        {"from": "alice@example.com", "to": "missing@example.com", "message": "Hello"}
    ])

    export = build_export(tmp_path)

    assert export["ready"] is False
    assert export["sql"] == ""
    assert export["errors"][0]["code"] == "missing_user_refs"


def test_postgres_sql_export_rejects_non_numeric_feed_post_ids(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com", "password": "hashed"}])
    write_json(tmp_path / "database" / "feed_data.json", {
        "posts": [{"id": "legacy-slug", "email": "alice@example.com", "text": "Post"}]
    })

    export = build_export(tmp_path)

    assert export["ready"] is False
    assert any(
        item.get("source") == "feed_posts" and "positive integer" in item.get("reason", "")
        for item in export["errors"]
    )
