import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.json_migration_inventory import as_dict, as_list, build_inventory, load_json, normalized_email


IMPORT_ORDER = [
    "users",
    "user_ai_settings",
    "privacy_settings",
    "social_follows",
    "friendships",
    "friend_requests",
    "user_blocks",
    "user_restrictions",
    "hidden_story_authors",
    "notifications",
    "messages",
    "feed_posts",
    "feed_post_likes",
    "feed_post_saves",
    "feed_post_comments",
    "stories",
    "proof_items",
    "reports",
    "ai_core_memory",
    "ai_feed_learning",
    "verification_codes",
    "login_attempts",
    "security_events",
    "news_items",
    "realtime_presence",
    "realtime_typing",
    "call_signals",
]


def list_count(value):
    return len(as_list(value))


def dict_count(value):
    return len(as_dict(value))


def count_feed_interactions(posts):
    likes = 0
    saves = 0
    comments = 0

    for post in as_list(posts):
        if not isinstance(post, dict):
            continue
        likes += list_count(post.get("likes"))
        saves += list_count(post.get("saves"))
        comments += list_count(post.get("comments"))

    return likes, saves, comments


def build_import_plan(root):
    root = Path(root)
    inventory = build_inventory(root)

    users = as_list(load_json(root / "users.json", []))
    user_ai_settings = as_dict(load_json(root / "database" / "user_ai_settings.json", {}))
    privacy = as_dict(load_json(root / "database" / "privacy_data.json", {}))
    privacy_users = as_dict(privacy.get("users")) if "users" in privacy else privacy

    social = as_dict(load_json(root / "social.json", {}))
    blocks = as_dict(load_json(root / "blocks.json", {"blocks": {}}))
    restrictions = as_dict(load_json(root / "restrictions.json", {"restrictions": {}}))
    hidden_stories = as_dict(load_json(root / "hidden_stories.json", {"hidden_stories": {}}))

    notifications_data = load_json(root / "notifications.json", {"notifications": []})
    notifications = notifications_data.get("notifications", []) if isinstance(notifications_data, dict) else notifications_data
    messages = as_list(load_json(root / "messages.json", []))

    feed = as_dict(load_json(root / "database" / "feed_data.json", {"posts": []}))
    posts = as_list(feed.get("posts"))
    post_likes, post_saves, post_comments = count_feed_interactions(posts)
    stories = as_dict(load_json(root / "stories.json", {"stories": []}))
    proofs = as_dict(load_json(root / "database" / "proof_data.json", {"proofs": []}))
    reports = as_dict(load_json(root / "reports.json", {"reports": []}))

    ai_core_memory = as_dict(load_json(root / "ai_core_memory.json", {}))
    ai_feed_learning = as_dict(load_json(root / "ai_feed_learning.json", {}))
    verification_codes = as_dict(load_json(root / "verification_codes.json", {}))
    login_attempts = as_dict(load_json(root / "login_attempts.json", {}))
    security_events = as_list(load_json(root / "security_log.json", []))
    news_items = as_list(load_json(root / "news.json", []))
    presence = as_dict(load_json(root / "presence_status.json", {}))
    typing = as_dict(load_json(root / "typing_status.json", {}))
    call_signals = as_dict(load_json(root / "call_signals.json", {}))

    user_emails = {
        normalized_email(user.get("email"))
        for user in users
        if isinstance(user, dict) and normalized_email(user.get("email"))
    }

    duplicate_user_emails = sorted({
        email for email in user_emails
        if sum(1 for user in users if normalized_email(user.get("email")) == email) > 1
    })

    row_counts = {
        "users": len(users),
        "user_ai_settings": dict_count(user_ai_settings),
        "privacy_settings": dict_count(privacy_users),
        "social_follows": list_count(social.get("follows")),
        "friendships": list_count(social.get("friends")),
        "friend_requests": list_count(social.get("friend_requests")),
        "user_blocks": sum(list_count(value) for value in as_dict(blocks.get("blocks", blocks)).values()),
        "user_restrictions": sum(list_count(value) for value in as_dict(restrictions.get("restrictions", restrictions)).values()),
        "hidden_story_authors": sum(list_count(value) for value in as_dict(hidden_stories.get("hidden_stories", hidden_stories)).values()),
        "notifications": list_count(notifications),
        "messages": len(messages),
        "feed_posts": len(posts),
        "feed_post_likes": post_likes,
        "feed_post_saves": post_saves,
        "feed_post_comments": post_comments,
        "stories": list_count(stories.get("stories")),
        "proof_items": list_count(proofs.get("proofs")),
        "reports": list_count(reports.get("reports")),
        "ai_core_memory": sum(list_count(items) for items in ai_core_memory.values()),
        "ai_feed_learning": dict_count(ai_feed_learning),
        "verification_codes": dict_count(verification_codes),
        "login_attempts": dict_count(login_attempts),
        "security_events": len(security_events),
        "news_items": len(news_items),
        "realtime_presence": dict_count(presence),
        "realtime_typing": dict_count(typing),
        "call_signals": dict_count(call_signals),
    }

    blockers = []
    warnings = []

    if inventory["missing_user_refs_count"]:
        blockers.append({
            "code": "missing_user_refs",
            "message": "JSON data still references users that do not exist in users.json.",
            "count": inventory["missing_user_refs_count"],
        })

    if duplicate_user_emails:
        blockers.append({
            "code": "duplicate_user_emails",
            "message": "users.json contains duplicate normalized emails.",
            "emails": duplicate_user_emails,
        })

    if not user_emails:
        warnings.append({
            "code": "no_users",
            "message": "No users found; dependent tables will import as empty or be skipped.",
        })

    return {
        "ready": not blockers,
        "import_order": IMPORT_ORDER,
        "row_counts": row_counts,
        "blockers": blockers,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Build a safe JSON-to-database import plan.")
    parser.add_argument("--root", default=".", help="Project root containing JSON files.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    plan = build_import_plan(args.root)
    indent = 2 if args.pretty else None
    print(json.dumps(plan, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
