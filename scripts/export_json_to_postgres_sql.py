import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_json_import_plan import build_import_plan
from scripts.json_migration_inventory import as_dict, as_list, load_json, normalized_email


UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "ai-match-life")


def stable_uuid(kind, key):
    return str(uuid.uuid5(UUID_NAMESPACE, f"{kind}:{key}"))


def sql_text(value):
    if value is None:
        return "NULL"
    value = str(value).replace("'", "''")
    return f"'{value}'"


def sql_bool(value):
    return "TRUE" if value is True else "FALSE"


def sql_int(value, default="NULL"):
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return default


def sql_jsonb(value):
    return f"{sql_text(json.dumps(value, ensure_ascii=False))}::jsonb"


def sql_ts(value):
    parsed = parse_timestamp(value)
    return sql_text(parsed.strftime("%Y-%m-%d %H:%M:%S")) if parsed else "NULL"


def parse_timestamp(value):
    value = str(value or "").strip()
    if not value:
        return None

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y %H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def user_id_for_email(email):
    return stable_uuid("user", normalized_email(email))


def post_id_for(post):
    post_key = post.get("id") or "|".join([
        normalized_email(post.get("email") or post.get("author_email")),
        str(post.get("date") or post.get("created_at") or ""),
        str(post.get("text") or ""),
    ])
    return stable_uuid("feed_post", post_key)


def add_error(errors, source, reason, item):
    errors.append({
        "source": source,
        "reason": reason,
        "item": item,
    })


def values_sql(values):
    return ", ".join(values)


def insert_sql(table, columns, values, conflict="DO NOTHING"):
    return (
        f"INSERT INTO {table} ({', '.join(columns)})\n"
        f"VALUES ({values_sql(values)})\n"
        f"ON CONFLICT {conflict};"
    )


def build_export(root):
    root = Path(root)
    plan = build_import_plan(root)
    if not plan["ready"]:
        return {
            "ready": False,
            "sql": "",
            "errors": plan["blockers"],
            "summary": {"statements": 0},
        }

    errors = []
    statements = [
        "-- Generated JSON to PostgreSQL import for AI Match Life.",
        "-- Review before running against production.",
        "BEGIN;",
    ]

    users = as_list(load_json(root / "users.json", []))
    known_emails = {
        normalized_email(user.get("email"))
        for user in users
        if isinstance(user, dict) and normalized_email(user.get("email"))
    }

    for user in users:
        if not isinstance(user, dict):
            add_error(errors, "users", "User row is not an object.", user)
            continue

        email = normalized_email(user.get("email"))
        if not email:
            add_error(errors, "users", "User email is missing.", user)
            continue

        statements.append(insert_sql(
            "users",
            [
                "id", "email", "phone", "password_hash", "name", "age", "country", "bio",
                "profession", "looking_for", "languages", "goals", "interests", "skills",
                "trust_score", "verified", "profile_completed", "onboarding_completed",
                "onboarding_skipped", "account_verified", "account_verified_at",
                "account_verified_via", "created_at",
            ],
            [
                sql_text(user_id_for_email(email)),
                sql_text(email),
                sql_text(user.get("phone")) if user.get("phone") else "NULL",
                sql_text(user.get("password", "")),
                sql_text(user.get("name", "")),
                sql_int(user.get("age")),
                sql_text(user.get("country", "")),
                sql_text(user.get("bio", "")),
                sql_text(user.get("profession", "")),
                sql_text(user.get("looking_for", "")),
                sql_jsonb(as_list(user.get("languages"))),
                sql_jsonb(as_list(user.get("goals"))),
                sql_jsonb(as_list(user.get("interests"))),
                sql_jsonb(as_list(user.get("skills"))),
                sql_int(user.get("trust_score"), default="50"),
                sql_bool(user.get("verified") is True),
                sql_bool(user.get("profile_completed") is True),
                sql_bool(user.get("onboarding_completed") is True),
                sql_bool(user.get("onboarding_skipped") is True),
                sql_bool(user.get("account_verified", True) is True),
                sql_ts(user.get("account_verified_at")),
                sql_text(user.get("account_verified_via", "")),
                sql_ts(user.get("created_at")) if user.get("created_at") else "now()",
            ],
        ))

    export_social(root, known_emails, statements, errors)
    export_notifications(root, known_emails, statements, errors)
    export_messages(root, known_emails, statements, errors)
    export_feed(root, known_emails, statements, errors)
    export_stories(root, known_emails, statements, errors)
    export_reports(root, known_emails, statements, errors)
    export_ai_memory(root, known_emails, statements, errors)
    export_security(root, statements)

    statements.append("COMMIT;")
    return {
        "ready": True,
        "sql": "\n\n".join(statements) + "\n",
        "errors": errors,
        "summary": {
            "statements": max(len(statements) - 4, 0),
            "errors": len(errors),
        },
    }


def export_social(root, known_emails, statements, errors):
    social = as_dict(load_json(root / "social.json", {}))

    for item in as_list(social.get("follows")):
        follower = normalized_email(item.get("follower")) if isinstance(item, dict) else ""
        following = normalized_email(item.get("following")) if isinstance(item, dict) else ""
        if follower not in known_emails or following not in known_emails:
            add_error(errors, "social_follows", "Unknown follower/following.", item)
            continue
        statements.append(insert_sql(
            "social_follows",
            ["follower_id", "following_id"],
            [sql_text(user_id_for_email(follower)), sql_text(user_id_for_email(following))],
        ))

    for item in as_list(social.get("friends")):
        user = normalized_email(item.get("user")) if isinstance(item, dict) else ""
        friend = normalized_email(item.get("friend")) if isinstance(item, dict) else ""
        if user not in known_emails or friend not in known_emails:
            add_error(errors, "friendships", "Unknown friendship user.", item)
            continue
        first, second = sorted([user_id_for_email(user), user_id_for_email(friend)])
        statements.append(insert_sql(
            "friendships",
            ["user_low_id", "user_high_id"],
            [sql_text(first), sql_text(second)],
        ))

    for item in as_list(social.get("friend_requests")):
        sender = normalized_email(item.get("from")) if isinstance(item, dict) else ""
        receiver = normalized_email(item.get("to")) if isinstance(item, dict) else ""
        if sender not in known_emails or receiver not in known_emails:
            add_error(errors, "friend_requests", "Unknown friend request user.", item)
            continue
        statements.append(insert_sql(
            "friend_requests",
            ["id", "sender_id", "receiver_id", "status"],
            [
                sql_text(stable_uuid("friend_request", f"{sender}->{receiver}")),
                sql_text(user_id_for_email(sender)),
                sql_text(user_id_for_email(receiver)),
                sql_text(item.get("status", "pending")),
            ],
        ))


def export_notifications(root, known_emails, statements, errors):
    data = load_json(root / "notifications.json", {"notifications": []})
    notifications = data.get("notifications", []) if isinstance(data, dict) else data

    for index, item in enumerate(as_list(notifications)):
        if not isinstance(item, dict):
            add_error(errors, "notifications", "Notification row is not an object.", item)
            continue
        target = normalized_email(item.get("email") or item.get("to"))
        sender = normalized_email(item.get("from_email") or item.get("from"))
        if target not in known_emails:
            add_error(errors, "notifications", "Unknown notification target.", item)
            continue
        from_user_id = sql_text(user_id_for_email(sender)) if sender in known_emails else "NULL"
        created = item.get("created_at_iso") or item.get("created_at")
        statements.append(insert_sql(
            "notifications",
            ["id", "user_id", "from_user_id", "type", "text", "status", "read", "created_at"],
            [
                sql_text(stable_uuid("notification", f"{target}:{index}:{created}:{item.get('text', '')}")),
                sql_text(user_id_for_email(target)),
                from_user_id,
                sql_text(item.get("type", "system")),
                sql_text(item.get("text", "")),
                sql_text(item.get("status", "")),
                sql_bool(item.get("read") is True),
                sql_ts(created) if created else "now()",
            ],
        ))


def export_messages(root, known_emails, statements, errors):
    messages = as_list(load_json(root / "messages.json", []))
    for item in messages:
        if not isinstance(item, dict):
            add_error(errors, "messages", "Message row is not an object.", item)
            continue
        sender = normalized_email(item.get("from"))
        receiver = normalized_email(item.get("to"))
        if sender not in known_emails or receiver not in known_emails:
            add_error(errors, "messages", "Unknown message participant.", item)
            continue
        message_id = sql_int(item.get("id")) if item.get("id") is not None else "DEFAULT"
        statements.append(insert_sql(
            "messages",
            [
                "id", "sender_id", "receiver_id", "message", "media_url", "media_type",
                "media_name", "status", "deleted_for_everyone", "deleted_for", "created_at",
            ],
            [
                message_id,
                sql_text(user_id_for_email(sender)),
                sql_text(user_id_for_email(receiver)),
                sql_text(item.get("message", "")),
                sql_text(item.get("media_url", "")),
                sql_text(item.get("media_type", "")),
                sql_text(item.get("media_name", "")),
                sql_text(item.get("status", "sent")),
                sql_bool(item.get("deleted_for_everyone") is True),
                sql_jsonb(as_list(item.get("deleted_for"))),
                sql_ts(item.get("time")) if item.get("time") else "now()",
            ],
        ))


def export_feed(root, known_emails, statements, errors):
    feed = as_dict(load_json(root / "database" / "feed_data.json", {"posts": []}))
    for post in as_list(feed.get("posts")):
        if not isinstance(post, dict):
            add_error(errors, "feed_posts", "Feed post is not an object.", post)
            continue
        author = normalized_email(post.get("email") or post.get("author_email"))
        if author not in known_emails:
            add_error(errors, "feed_posts", "Unknown post author.", post)
            continue
        post_id = post_id_for(post)
        media = []
        if post.get("media_url"):
            media.append({
                "url": post.get("media_url", ""),
                "type": post.get("media_type", ""),
                "name": post.get("media_name", ""),
            })
        statements.append(insert_sql(
            "feed_posts",
            ["id", "author_id", "type", "text", "language", "location", "hashtags", "media", "created_at"],
            [
                sql_text(post_id),
                sql_text(user_id_for_email(author)),
                sql_text(post.get("type", "Идея")),
                sql_text(post.get("text", "")),
                sql_text(post.get("language", "unknown")),
                sql_text(post.get("location", "")),
                sql_jsonb(as_list(post.get("hashtags"))),
                sql_jsonb(media),
                sql_ts(post.get("created_at") or post.get("date")) if (post.get("created_at") or post.get("date")) else "now()",
            ],
        ))
        for email in as_list(post.get("likes")):
            email = normalized_email(email)
            if email in known_emails:
                statements.append(insert_sql(
                    "feed_post_likes",
                    ["post_id", "user_id"],
                    [sql_text(post_id), sql_text(user_id_for_email(email))],
                ))
        for email in as_list(post.get("saves")):
            email = normalized_email(email)
            if email in known_emails:
                statements.append(insert_sql(
                    "feed_post_saves",
                    ["post_id", "user_id"],
                    [sql_text(post_id), sql_text(user_id_for_email(email))],
                ))
        for index, comment in enumerate(as_list(post.get("comments"))):
            if not isinstance(comment, dict):
                continue
            commenter = normalized_email(comment.get("author") or comment.get("email"))
            if commenter not in known_emails:
                add_error(errors, "feed_post_comments", "Unknown comment author.", comment)
                continue
            statements.append(insert_sql(
                "feed_post_comments",
                ["id", "post_id", "user_id", "text", "created_at"],
                [
                    sql_text(stable_uuid("feed_comment", f"{post_id}:{index}:{comment.get('text', '')}")),
                    sql_text(post_id),
                    sql_text(user_id_for_email(commenter)),
                    sql_text(comment.get("text", "")),
                    sql_ts(comment.get("created_at") or comment.get("date")) if (comment.get("created_at") or comment.get("date")) else "now()",
                ],
            ))


def export_stories(root, known_emails, statements, errors):
    data = as_dict(load_json(root / "stories.json", {"stories": []}))
    for story in as_list(data.get("stories")):
        if not isinstance(story, dict):
            add_error(errors, "stories", "Story row is not an object.", story)
            continue
        author = normalized_email(story.get("email") or story.get("author_email"))
        if author not in known_emails:
            add_error(errors, "stories", "Unknown story author.", story)
            continue
        created = parse_timestamp(story.get("created_at"))
        expires = created + timedelta(hours=24) if created else None
        statements.append(insert_sql(
            "stories",
            ["id", "author_id", "media_url", "media_type", "text", "created_at", "expires_at"],
            [
                sql_text(stable_uuid("story", story.get("id") or f"{author}:{story.get('created_at', '')}")),
                sql_text(user_id_for_email(author)),
                sql_text(story.get("media_url", "")),
                sql_text(story.get("media_type", "")),
                sql_text(story.get("text", "")),
                sql_text(created.strftime("%Y-%m-%d %H:%M:%S")) if created else "now()",
                sql_text(expires.strftime("%Y-%m-%d %H:%M:%S")) if expires else "now() + interval '24 hours'",
            ],
        ))


def export_reports(root, known_emails, statements, errors):
    data = as_dict(load_json(root / "reports.json", {"reports": []}))
    for index, report in enumerate(as_list(data.get("reports"))):
        if not isinstance(report, dict):
            add_error(errors, "reports", "Report row is not an object.", report)
            continue
        reporter = normalized_email(report.get("reporter_email") or report.get("reporter"))
        target = normalized_email(report.get("target_email") or report.get("target"))
        reviewer = normalized_email(report.get("reviewed_by"))
        if reporter not in known_emails or target not in known_emails:
            add_error(errors, "reports", "Unknown report reporter or target.", report)
            continue

        reviewed_by_id = sql_text(user_id_for_email(reviewer)) if reviewer in known_emails else "NULL"
        report_key = report.get("id") or f"{reporter}:{target}:{index}:{report.get('created_at', '')}"
        statements.append(insert_sql(
            "reports",
            [
                "id", "reporter_id", "target_user_id", "reason", "details", "status",
                "reviewed_by_id", "reviewed_at", "moderation_note", "action", "created_at", "updated_at",
            ],
            [
                sql_text(stable_uuid("report", report_key)),
                sql_text(user_id_for_email(reporter)),
                sql_text(user_id_for_email(target)),
                sql_text(report.get("reason", "")),
                sql_text(report.get("details", "")),
                sql_text(report.get("status", "new")),
                reviewed_by_id,
                sql_ts(report.get("reviewed_at")) if report.get("reviewed_at") else "NULL",
                sql_text(report.get("moderation_note", "")),
                sql_text(report.get("action", "")),
                sql_ts(report.get("created_at")) if report.get("created_at") else "now()",
                sql_ts(report.get("updated_at")) if report.get("updated_at") else "now()",
            ],
        ))


def export_ai_memory(root, known_emails, statements, errors):
    memory = as_dict(load_json(root / "ai_core_memory.json", {}))
    for email, items in memory.items():
        email = normalized_email(email)
        if email not in known_emails:
            add_error(errors, "ai_core_memory", "Unknown AI memory user.", {email: items})
            continue
        for index, item in enumerate(as_list(items)):
            if not isinstance(item, dict):
                continue
            statements.append(insert_sql(
                "ai_core_memory",
                ["id", "user_id", "mode", "question", "answer", "created_at"],
                [
                    sql_text(stable_uuid("ai_core_memory", f"{email}:{index}:{item.get('time', '')}")),
                    sql_text(user_id_for_email(email)),
                    sql_text(item.get("mode", "")),
                    sql_text(item.get("question", "")),
                    sql_text(item.get("answer", "")),
                    sql_ts(item.get("time")) if item.get("time") else "now()",
                ],
            ))

    feed_learning = as_dict(load_json(root / "ai_feed_learning.json", {}))
    for email, data in feed_learning.items():
        email = normalized_email(email)
        if email not in known_emails or not isinstance(data, dict):
            add_error(errors, "ai_feed_learning", "Unknown AI feed learning user.", {email: data})
            continue
        statements.append(insert_sql(
            "ai_feed_learning",
            ["user_id", "languages", "types", "hashtags", "locations", "actions", "updated_at"],
            [
                sql_text(user_id_for_email(email)),
                sql_jsonb(as_dict(data.get("languages"))),
                sql_jsonb(as_dict(data.get("types"))),
                sql_jsonb(as_dict(data.get("hashtags"))),
                sql_jsonb(as_dict(data.get("locations"))),
                sql_jsonb(as_list(data.get("actions"))),
                sql_ts(data.get("updated_at")) if data.get("updated_at") else "now()",
            ],
        ))


def export_security(root, statements):
    events = as_list(load_json(root / "security_log.json", []))
    for event in events:
        if not isinstance(event, dict):
            continue
        statements.append(insert_sql(
            "security_events",
            ["event", "email", "ip", "details", "created_at"],
            [
                sql_text(event.get("event", "")),
                sql_text(normalized_email(event.get("email"))),
                sql_text(event.get("ip", "")),
                sql_text(event.get("details", "")),
                sql_ts(event.get("time")) if event.get("time") else "now()",
            ],
            conflict="DO NOTHING",
        ))


def write_export(output_path, errors_path, export):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(export["sql"], encoding="utf-8")
    errors_path.write_text(json.dumps(export["errors"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Export cleaned JSON data to PostgreSQL import SQL.")
    parser.add_argument("--root", default=".", help="Project root containing JSON files.")
    parser.add_argument("--output", default="database/import/generated_import.sql", help="SQL output path.")
    parser.add_argument("--errors-output", default="database/import/import_errors.json", help="Import error report path.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print summary output.")
    args = parser.parse_args()

    export = build_export(args.root)
    if export["ready"]:
        write_export(Path(args.output), Path(args.errors_output), export)

    summary = {
        "ready": export["ready"],
        "output": args.output if export["ready"] else "",
        "errors_output": args.errors_output if export["ready"] else "",
        "summary": export["summary"],
        "errors": export["errors"][:20],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
