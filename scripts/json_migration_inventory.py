import argparse
import json
from pathlib import Path


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


def normalized_email(value):
    return str(value or "").strip().lower()


def build_inventory(root):
    root = Path(root)

    users = as_list(load_json(root / "users.json", []))
    user_emails = {
        normalized_email(user.get("email"))
        for user in users
        if isinstance(user, dict) and normalized_email(user.get("email"))
    }

    social = as_dict(load_json(root / "social.json", {}))
    feed = as_dict(load_json(root / "database" / "feed_data.json", {"posts": []}))
    notifications_data = load_json(root / "notifications.json", {"notifications": []})
    notifications = (
        notifications_data.get("notifications", [])
        if isinstance(notifications_data, dict)
        else notifications_data
    )

    messages = as_list(load_json(root / "messages.json", []))
    stories = as_dict(load_json(root / "stories.json", {"stories": []}))
    proofs = as_dict(load_json(root / "database" / "proof_data.json", {"proofs": []}))
    reports = as_dict(load_json(root / "reports.json", {"reports": []}))

    missing_user_refs = []

    def track_email(source, email):
        email = normalized_email(email)
        if email and email not in user_emails:
            missing_user_refs.append({"source": source, "email": email})

    for message in messages:
        if isinstance(message, dict):
            track_email("messages.from", message.get("from"))
            track_email("messages.to", message.get("to"))

    for follow in as_list(social.get("follows")):
        if isinstance(follow, dict):
            track_email("social.follows.follower", follow.get("follower"))
            track_email("social.follows.following", follow.get("following"))

    for friendship in as_list(social.get("friends")):
        if isinstance(friendship, dict):
            track_email("social.friends.user", friendship.get("user"))
            track_email("social.friends.friend", friendship.get("friend"))

    for request in as_list(social.get("friend_requests")):
        if isinstance(request, dict):
            track_email("social.friend_requests.from", request.get("from"))
            track_email("social.friend_requests.to", request.get("to"))

    for post in as_list(feed.get("posts")):
        if isinstance(post, dict):
            track_email("feed.posts.email", post.get("email") or post.get("author_email"))

    return {
        "counts": {
            "users": len(users),
            "messages": len(messages),
            "social_follows": len(as_list(social.get("follows"))),
            "friendships": len(as_list(social.get("friends"))),
            "friend_requests": len(as_list(social.get("friend_requests"))),
            "feed_posts": len(as_list(feed.get("posts"))),
            "notifications": len(as_list(notifications)),
            "stories": len(as_list(stories.get("stories"))),
            "proof_items": len(as_list(proofs.get("proofs"))),
            "reports": len(as_list(reports.get("reports"))),
        },
        "missing_user_refs": missing_user_refs[:200],
        "missing_user_refs_count": len(missing_user_refs),
    }


def main():
    parser = argparse.ArgumentParser(description="Inspect JSON data before database migration.")
    parser.add_argument("--root", default=".", help="Project root containing JSON files.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    inventory = build_inventory(args.root)
    indent = 2 if args.pretty else None
    print(json.dumps(inventory, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
