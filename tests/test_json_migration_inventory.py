import json

from scripts.json_migration_inventory import build_inventory


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_json_migration_inventory_counts_core_records(tmp_path):
    write_json(tmp_path / "users.json", [{"email": "alice@example.com"}])
    write_json(tmp_path / "messages.json", [
        {"from": "alice@example.com", "to": "bob@example.com"}
    ])
    write_json(tmp_path / "social.json", {
        "follows": [{"follower": "alice@example.com", "following": "bob@example.com"}],
        "friends": [],
        "friend_requests": [],
    })
    write_json(tmp_path / "database" / "feed_data.json", {
        "posts": [{"email": "alice@example.com"}]
    })
    write_json(tmp_path / "notifications.json", {"notifications": [{"email": "alice@example.com"}]})
    write_json(tmp_path / "stories.json", {"stories": [{"email": "alice@example.com"}]})
    write_json(tmp_path / "database" / "proof_data.json", {"proofs": [{"email": "alice@example.com"}]})
    write_json(tmp_path / "reports.json", {"reports": [{"reporter_email": "alice@example.com"}]})

    inventory = build_inventory(tmp_path)

    assert inventory["counts"]["users"] == 1
    assert inventory["counts"]["messages"] == 1
    assert inventory["counts"]["social_follows"] == 1
    assert inventory["counts"]["feed_posts"] == 1
    assert inventory["counts"]["notifications"] == 1
    assert inventory["missing_user_refs_count"] == 2


def test_json_migration_inventory_handles_missing_files(tmp_path):
    inventory = build_inventory(tmp_path)

    assert inventory["counts"]["users"] == 0
    assert inventory["counts"]["messages"] == 0
    assert inventory["missing_user_refs_count"] == 0
