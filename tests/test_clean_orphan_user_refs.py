import json

from scripts.clean_orphan_user_refs import build_cleanup


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_clean_orphan_user_refs_removes_missing_user_records(tmp_path):
    write_json(tmp_path / "users.json", [
        {"email": "alice@example.com"},
        {"email": "bob@example.com"},
    ])
    write_json(tmp_path / "messages.json", [
        {"from": "alice@example.com", "to": "bob@example.com"},
        {"from": "missing@example.com", "to": "bob@example.com"},
    ])
    write_json(tmp_path / "social.json", {
        "follows": [{"follower": "missing@example.com", "following": "bob@example.com"}],
        "friends": [{"user": "alice@example.com", "friend": "bob@example.com"}],
        "friend_requests": [{"from": "alice@example.com", "to": "missing@example.com"}],
    })
    write_json(tmp_path / "database" / "feed_data.json", {
        "posts": [
            {
                "email": "alice@example.com",
                "likes": ["missing@example.com", "bob@example.com"],
                "saves": ["missing@example.com"],
                "comments": [
                    {"author": "missing@example.com"},
                    {"author": "bob@example.com"},
                ],
            },
            {"email": "missing@example.com"},
        ]
    })
    write_json(tmp_path / "notifications.json", {
        "notifications": [
            {"email": "alice@example.com", "from": "missing@example.com"},
            {"email": "alice@example.com", "from": "bob@example.com"},
        ]
    })
    write_json(tmp_path / "stories.json", {
        "stories": [
            {
                "email": "alice@example.com",
                "viewers": ["missing@example.com", "bob@example.com"],
                "views": ["missing@example.com", "bob@example.com"],
            },
            {"email": "missing@example.com", "viewers": []},
        ]
    })

    cleanup = build_cleanup(tmp_path)

    assert cleanup["total_removed"] == 11

    messages = cleanup["files"][0]["data"]
    assert messages == [{"from": "alice@example.com", "to": "bob@example.com"}]

    social = cleanup["files"][1]["data"]
    assert social["follows"] == []
    assert social["friend_requests"] == []
    assert social["friends"] == [{"user": "alice@example.com", "friend": "bob@example.com"}]

    feed = cleanup["files"][2]["data"]
    assert len(feed["posts"]) == 1
    assert feed["posts"][0]["likes"] == ["bob@example.com"]
    assert feed["posts"][0]["saves"] == []
    assert feed["posts"][0]["comments"] == [{"author": "bob@example.com"}]

    stories = cleanup["files"][4]["data"]
    assert stories["stories"][0]["viewers"] == ["bob@example.com"]
    assert stories["stories"][0]["views"] == ["bob@example.com"]


def test_clean_orphan_user_refs_is_noop_for_clean_data(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "messages.json", [])
    write_json(tmp_path / "social.json", {"follows": [], "friends": [], "friend_requests": []})
    write_json(tmp_path / "database" / "feed_data.json", {"posts": []})
    write_json(tmp_path / "notifications.json", {"notifications": []})
    write_json(tmp_path / "stories.json", {"stories": []})

    cleanup = build_cleanup(tmp_path)

    assert cleanup["total_removed"] == 0
    assert all(result["changed"] is False for result in cleanup["files"])
