from datetime import datetime

from backend.repositories.notification_repository import get_notification_repository, normalize_notifications_data


NOTIFICATIONS_FILE = "notifications.json"


def _normalize_email(value):
    return str(value or "").strip().lower()


def load_notifications():
    return get_notification_repository(NOTIFICATIONS_FILE).load_all()


def save_notifications(data):
    get_notification_repository(NOTIFICATIONS_FILE).save_all(normalize_notifications_data(data))


def add_notification(email, text, notification_type="system", from_email=""):
    email = _normalize_email(email)
    from_email = _normalize_email(from_email)

    if not email:
        return

    now = datetime.now()
    data = load_notifications()
    notifications = data.get("notifications", [])

    notifications.insert(0, {
        "email": email,
        "from": from_email,
        "from_email": from_email,
        "type": str(notification_type or "system"),
        "text": str(text or "").strip(),
        "read": False,
        "created_at": now.strftime("%Y-%m-%d %H:%M"),
        "created_at_iso": now.strftime("%Y-%m-%d %H:%M:%S"),
        "time_label": now.strftime("%H:%M")
    })

    data["notifications"] = notifications
    save_notifications(data)


def get_notifications(email):
    email = _normalize_email(email)
    data = load_notifications()
    notifications = data.get("notifications", [])
    result = []

    for item in notifications:
        if isinstance(item, dict):
            item_email = _normalize_email(item.get("email", ""))
            item_to = _normalize_email(item.get("to", ""))

            if item_email == email or item_to == email:
                normalized_item = dict(item)
                normalized_item.setdefault("text", "")
                normalized_item.setdefault("created_at", "")
                normalized_item.setdefault("type", "system")
                normalized_item.setdefault("read", False)
                result.append(normalized_item)

        elif isinstance(item, str):
            result.append({
                "email": email,
                "from": "",
                "from_email": "",
                "type": "system",
                "text": item,
                "read": False,
                "created_at": "",
                "time_label": ""
            })

    return result


def count_unread_notifications(email):
    return sum(1 for item in get_notifications(email) if not item.get("read", False))


def mark_notifications_read(email):
    email = _normalize_email(email)
    data = load_notifications()
    notifications = data.get("notifications", [])

    for item in notifications:
        if not isinstance(item, dict):
            continue

        item_email = _normalize_email(item.get("email", ""))
        item_to = _normalize_email(item.get("to", ""))

        if item_email == email or item_to == email:
            item["read"] = True

    data["notifications"] = notifications
    save_notifications(data)
