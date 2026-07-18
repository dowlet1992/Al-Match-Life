def normalize_email(value):
    return str(value or "").strip().lower()


def next_message_id(messages):
    numeric_ids = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        try:
            numeric_ids.append(int(message.get("id", 0)))
        except Exception:
            continue

    return max(numeric_ids) + 1 if numeric_ids else 1


def visible_chat_messages(messages, current_email, other_email):
    current_email = normalize_email(current_email)
    other_email = normalize_email(other_email)
    visible_messages = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("deleted_for_everyone") is True:
            continue
        if current_email in message.get("deleted_for", []):
            continue

        sender_email = normalize_email(message.get("from", ""))
        receiver_email = normalize_email(message.get("to", ""))

        if (
            sender_email == current_email and receiver_email == other_email
        ) or (
            sender_email == other_email and receiver_email == current_email
        ):
            visible_messages.append(message)

    return visible_messages


def create_text_message(sender_email, receiver_email, text, reply_to="", time_text=""):
    return {
        "id": None,
        "from": sender_email,
        "to": receiver_email,
        "message": text,
        "media_url": "",
        "media_type": "",
        "media_name": "",
        "reply_to": reply_to,
        "time": time_text,
        "status": "sent",
    }


def append_message(messages, message):
    if not isinstance(messages, list):
        messages = []

    message["id"] = next_message_id(messages)
    messages.append(message)
    return message


def chat_summaries(messages, current_email, find_user, is_blocked):
    current_email = normalize_email(current_email)
    conversations = {}

    for message in messages:
        if not isinstance(message, dict) or message.get("deleted_for_everyone") is True:
            continue

        sender_email = normalize_email(message.get("from", ""))
        receiver_email = normalize_email(message.get("to", ""))

        if sender_email == current_email:
            other_email = receiver_email
        elif receiver_email == current_email:
            other_email = sender_email
        else:
            continue

        other_user = find_user(other_email)
        if other_user is None:
            continue

        if is_blocked(current_email, other_email) or is_blocked(other_email, current_email):
            continue

        conversations[other_email] = {
            "user": other_user,
            "last_message": message,
        }

    return list(conversations.values())
