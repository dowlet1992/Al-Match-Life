import json
from datetime import datetime


def load_notifications(filename="notifications.json"):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return []


def save_notifications(notifications, filename="notifications.json"):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(notifications, file, indent=4, ensure_ascii=False)


def add_notification(to_email, from_email, notification_type, text):
    notifications = load_notifications()

    notifications.append({
        "to": to_email.strip().lower(),
        "from": from_email.strip().lower(),
        "type": notification_type,
        "text": text,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "read": False
    })

    save_notifications(notifications)


def get_notifications(email):
    email = email.strip().lower()
    notifications = load_notifications()

    user_notifications = []

    for item in notifications:
        if item.get("to") == email:
            user_notifications.append(item)

    return list(reversed(user_notifications))