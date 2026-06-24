import json
from backend.models import User


def save_users_to_json(users, filename="users.json"):
    data = []

    for user in users:
        data.append(user.info())

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def load_users_from_json(filename="users.json"):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
    except:
        return None

    users = []

    for item in data:
        users.append(
            User(
                item.get("name"),
                item.get("age"),
                item.get("email"),
                item.get("password"),
                item.get("country"),
                item.get("bio"),
                item.get("profession", ""),
                item.get("looking_for", ""),
                item.get("languages", []),
                item.get("goals", []),
                item.get("interests", []),
                item.get("skills", []),
                item.get("trust_score", 50),
                item.get("verified", False),
                item.get("profile_completed", False),
                item.get("created_at")
            )
        )

    return users