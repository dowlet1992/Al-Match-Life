import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path


def load_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)
        file.write("\n")


def normalized_email(value):
    return str(value or "").strip().lower()


def is_known_email(value, known_emails):
    email = normalized_email(value)
    return bool(email and email in known_emails)


def backup_file(path, backup_dir):
    if path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_dir / path.name)


def clean_messages(root, known_emails):
    path = root / "messages.json"
    messages = load_json(path, [])
    if not isinstance(messages, list):
        return {"path": str(path), "removed": 0, "changed": False, "data": messages}

    cleaned = [
        message for message in messages
        if isinstance(message, dict)
        and is_known_email(message.get("from"), known_emails)
        and is_known_email(message.get("to"), known_emails)
    ]
    return {
        "path": str(path),
        "removed": len(messages) - len(cleaned),
        "changed": len(messages) != len(cleaned),
        "data": cleaned,
    }


def clean_social(root, known_emails):
    path = root / "social.json"
    social = load_json(path, {})
    if not isinstance(social, dict):
        social = {}

    follows = social.get("follows", [])
    friends = social.get("friends", [])
    requests = social.get("friend_requests", [])

    cleaned_follows = [
        item for item in follows if isinstance(item, dict)
        and is_known_email(item.get("follower"), known_emails)
        and is_known_email(item.get("following"), known_emails)
    ]
    cleaned_friends = [
        item for item in friends if isinstance(item, dict)
        and is_known_email(item.get("user"), known_emails)
        and is_known_email(item.get("friend"), known_emails)
    ]
    cleaned_requests = [
        item for item in requests if isinstance(item, dict)
        and is_known_email(item.get("from"), known_emails)
        and is_known_email(item.get("to"), known_emails)
    ]

    cleaned = dict(social)
    cleaned["follows"] = cleaned_follows
    cleaned["friends"] = cleaned_friends
    cleaned["friend_requests"] = cleaned_requests

    removed = (
        len(follows) - len(cleaned_follows)
        + len(friends) - len(cleaned_friends)
        + len(requests) - len(cleaned_requests)
    )
    return {"path": str(path), "removed": removed, "changed": removed > 0, "data": cleaned}


def clean_feed(root, known_emails):
    path = root / "database" / "feed_data.json"
    feed = load_json(path, {"posts": []})
    if not isinstance(feed, dict):
        feed = {"posts": []}

    posts = feed.get("posts", [])
    cleaned_posts = []
    removed_posts = 0
    removed_likes = 0
    removed_saves = 0
    removed_comments = 0

    for post in posts if isinstance(posts, list) else []:
        if not isinstance(post, dict):
            continue

        author_email = post.get("email") or post.get("author_email")
        if not is_known_email(author_email, known_emails):
            removed_posts += 1
            continue

        likes = post.get("likes", [])
        saves = post.get("saves", [])
        comments = post.get("comments", [])

        cleaned_likes = [email for email in likes if is_known_email(email, known_emails)]
        cleaned_saves = [email for email in saves if is_known_email(email, known_emails)]
        cleaned_comments = [
            comment for comment in comments
            if isinstance(comment, dict)
            and is_known_email(comment.get("author") or comment.get("email"), known_emails)
        ]

        removed_likes += len(likes) - len(cleaned_likes) if isinstance(likes, list) else 0
        removed_saves += len(saves) - len(cleaned_saves) if isinstance(saves, list) else 0
        removed_comments += len(comments) - len(cleaned_comments) if isinstance(comments, list) else 0

        cleaned_post = dict(post)
        cleaned_post["likes"] = cleaned_likes
        cleaned_post["saves"] = cleaned_saves
        cleaned_post["comments"] = cleaned_comments
        cleaned_posts.append(cleaned_post)

    cleaned_feed = dict(feed)
    cleaned_feed["posts"] = cleaned_posts
    removed = removed_posts + removed_likes + removed_saves + removed_comments
    return {
        "path": str(path),
        "removed": removed,
        "removed_posts": removed_posts,
        "removed_likes": removed_likes,
        "removed_saves": removed_saves,
        "removed_comments": removed_comments,
        "changed": removed > 0,
        "data": cleaned_feed,
    }


def clean_notifications(root, known_emails):
    path = root / "notifications.json"
    data = load_json(path, {"notifications": []})
    was_list = isinstance(data, list)
    notifications = data if was_list else data.get("notifications", []) if isinstance(data, dict) else []

    cleaned_notifications = []
    for item in notifications if isinstance(notifications, list) else []:
        if not isinstance(item, dict):
            continue
        target_ok = not normalized_email(item.get("email") or item.get("to")) or is_known_email(item.get("email") or item.get("to"), known_emails)
        sender_value = item.get("from_email") or item.get("from")
        sender_ok = not normalized_email(sender_value) or is_known_email(sender_value, known_emails)
        if target_ok and sender_ok:
            cleaned_notifications.append(item)

    cleaned_data = cleaned_notifications if was_list else {"notifications": cleaned_notifications}
    return {
        "path": str(path),
        "removed": len(notifications) - len(cleaned_notifications) if isinstance(notifications, list) else 0,
        "changed": isinstance(notifications, list) and len(notifications) != len(cleaned_notifications),
        "data": cleaned_data,
    }


def clean_stories(root, known_emails):
    path = root / "stories.json"
    data = load_json(path, {"stories": []})
    if not isinstance(data, dict):
        data = {"stories": []}

    stories = data.get("stories", [])
    cleaned_stories = []
    removed_stories = 0
    removed_viewers = 0

    for story in stories if isinstance(stories, list) else []:
        if not isinstance(story, dict):
            continue
        if not is_known_email(story.get("email") or story.get("author_email"), known_emails):
            removed_stories += 1
            continue

        viewers = story.get("viewers", [])
        views = story.get("views", [])
        cleaned_viewers = [email for email in viewers if is_known_email(email, known_emails)]
        cleaned_views = [email for email in views if is_known_email(email, known_emails)]
        removed_viewers += len(viewers) - len(cleaned_viewers) if isinstance(viewers, list) else 0
        removed_viewers += len(views) - len(cleaned_views) if isinstance(views, list) else 0

        cleaned_story = dict(story)
        cleaned_story["viewers"] = cleaned_viewers
        cleaned_story["views"] = cleaned_views
        cleaned_stories.append(cleaned_story)

    cleaned_data = dict(data)
    cleaned_data["stories"] = cleaned_stories
    removed = removed_stories + removed_viewers
    return {
        "path": str(path),
        "removed": removed,
        "removed_stories": removed_stories,
        "removed_viewers": removed_viewers,
        "changed": removed > 0,
        "data": cleaned_data,
    }


def build_cleanup(root):
    root = Path(root)
    users = load_json(root / "users.json", [])
    known_emails = {
        normalized_email(user.get("email"))
        for user in users
        if isinstance(user, dict) and normalized_email(user.get("email"))
    }

    results = [
        clean_messages(root, known_emails),
        clean_social(root, known_emails),
        clean_feed(root, known_emails),
        clean_notifications(root, known_emails),
        clean_stories(root, known_emails),
    ]

    return {
        "known_users": len(known_emails),
        "total_removed": sum(result["removed"] for result in results),
        "files": results,
    }


def apply_cleanup(root, cleanup):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(root) / "backups" / f"orphan_cleanup_{timestamp}"

    for result in cleanup["files"]:
        path = Path(result["path"])
        if result["changed"]:
            backup_file(path, backup_dir)
            save_json(path, result["data"])

    return backup_dir


def serializable_summary(cleanup):
    return {
        "known_users": cleanup["known_users"],
        "total_removed": cleanup["total_removed"],
        "files": [
            {key: value for key, value in result.items() if key != "data"}
            for result in cleanup["files"]
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Clean JSON records that reference missing users.")
    parser.add_argument("--root", default=".", help="Project root containing JSON files.")
    parser.add_argument("--apply", action="store_true", help="Write cleaned JSON files and create backups.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    cleanup = build_cleanup(args.root)
    summary = serializable_summary(cleanup)

    if args.apply:
        backup_dir = apply_cleanup(args.root, cleanup)
        summary["applied"] = True
        summary["backup_dir"] = str(backup_dir)
    else:
        summary["applied"] = False

    indent = 2 if args.pretty else None
    print(json.dumps(summary, ensure_ascii=False, indent=indent))


if __name__ == "__main__":
    main()
