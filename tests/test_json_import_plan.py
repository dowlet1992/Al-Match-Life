import json

from scripts.build_json_import_plan import build_import_plan


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_json_import_plan_counts_rows_for_clean_data(tmp_path):
    write_json(tmp_path / "users.json", [
        {"email": "alice@example.com"},
        {"email": "bob@example.com"},
    ])
    write_json(tmp_path / "messages.json", [
        {"from": "alice@example.com", "to": "bob@example.com"}
    ])
    write_json(tmp_path / "social.json", {
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}],
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "friend_requests": [],
    })
    write_json(tmp_path / "database" / "feed_data.json", {
        "posts": [
            {
                "email": "alice@example.com",
                "likes": ["bob@example.com"],
                "saves": ["bob@example.com"],
                "comments": [{"author": "bob@example.com"}],
            }
        ]
    })
    write_json(tmp_path / "notifications.json", {"notifications": []})
    write_json(tmp_path / "stories.json", {"stories": []})
    write_json(tmp_path / "auth_refresh_sessions.json", {
        "token-1": {"email": "alice@example.com", "token_hash": "hash"}
    })
    write_json(tmp_path / "push_devices.json", {"devices": [
        {"email": "alice@example.com", "device_id": "browser-1"}
    ]})

    plan = build_import_plan(tmp_path)

    assert plan["ready"] is True
    assert plan["blockers"] == []
    assert plan["row_counts"]["users"] == 2
    assert plan["row_counts"]["messages"] == 1
    assert plan["row_counts"]["auth_refresh_sessions"] == 1
    assert plan["row_counts"]["push_devices"] == 1
    assert plan["row_counts"]["social_follows"] == 1
    assert plan["row_counts"]["feed_posts"] == 1
    assert plan["row_counts"]["feed_post_likes"] == 1
    assert plan["row_counts"]["feed_post_saves"] == 1
    assert plan["row_counts"]["feed_post_comments"] == 1
    assert plan["import_order"][0] == "users"
    assert plan["import_order"].index("auth_refresh_sessions") < plan["import_order"].index("messages")


def test_json_import_plan_blocks_orphan_session_and_push_device_owners(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "auth_refresh_sessions.json", {
        "token-1": {"email": "missing@example.com"}
    })
    write_json(tmp_path / "push_devices.json", {"devices": [
        {"email": "missing@example.com", "device_id": "browser-1"}
    ]})

    plan = build_import_plan(tmp_path)

    assert plan["ready"] is False
    blocker = next(item for item in plan["blockers"] if item["code"] == "missing_session_or_device_user_refs")
    assert blocker["count"] == 2


def test_json_import_plan_blocks_orphan_ai_memory_owners(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "ai_core_memory.json", {
        "missing@example.com": [{"question": "legacy"}]
    })
    write_json(tmp_path / "ai_feed_learning.json", {
        "missing@example.com": {"actions": []}
    })

    plan = build_import_plan(tmp_path)

    assert plan["ready"] is False
    blocker = next(item for item in plan["blockers"] if item["code"] == "missing_ai_memory_user_refs")
    assert blocker["count"] == 2
    assert plan["row_counts"]["ai_core_memory"] == 0
    assert plan["row_counts"]["ai_feed_learning"] == 0


def test_json_import_plan_blocks_missing_user_refs(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "messages.json", [
        {"from": "alice@example.com", "to": "missing@example.com"}
    ])

    plan = build_import_plan(tmp_path)

    assert plan["ready"] is False
    assert plan["blockers"][0]["code"] == "missing_user_refs"


def test_json_import_plan_blocks_duplicate_user_emails(tmp_path):
    write_json(tmp_path / "users.json", [
        {"email": "alice@example.com"},
        {"email": "ALICE@example.com"},
    ])

    plan = build_import_plan(tmp_path)

    assert plan["ready"] is False
    assert plan["blockers"][0]["code"] == "duplicate_user_emails"
