import json


DEFAULT_SETTINGS = {
    "receive_recommendations": True,
    "show_me_to_others": True,
    "show_in_search": True,
    "allow_messages": True,
    "verified_only_messages": False,
    "vip_mode": False
}


def load_privacy():
    try:
        with open("database/privacy_data.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {"users": {}}


def save_privacy(data):
    with open("database/privacy_data.json", "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def get_user_privacy(email):
    data = load_privacy()
    users = data.get("users", {})

    if email not in users:
        users[email] = DEFAULT_SETTINGS.copy()
        data["users"] = users
        save_privacy(data)

    return users[email]


def update_user_privacy(email, key, value):
    data = load_privacy()
    users = data.get("users", {})

    if email not in users:
        users[email] = DEFAULT_SETTINGS.copy()

    users[email][key] = value

    data["users"] = users
    save_privacy(data)

    return users[email]


def can_receive_recommendations(email):
    settings = get_user_privacy(email)
    return settings.get("receive_recommendations", True)


def can_be_recommended_to_others(email):
    settings = get_user_privacy(email)
    return settings.get("show_me_to_others", True)


def can_show_in_search(email):
    settings = get_user_privacy(email)
    return settings.get("show_in_search", True)


def can_receive_messages(email):
    settings = get_user_privacy(email)
    return settings.get("allow_messages", True)