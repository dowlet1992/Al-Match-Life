def normalize_email(value):
    return str(value or "").strip().lower()


def safe_account_payload(user):
    if user is None:
        return {}

    payload = user.info() if hasattr(user, "info") else dict(user)
    payload.pop("password", None)
    return payload


def social_snapshot_for_email(social_data, email):
    normalized_email = normalize_email(email)
    social_data = social_data if isinstance(social_data, dict) else {}
    return {
        "friends": [
            item for item in social_data.get("friends", [])
            if isinstance(item, dict)
            and normalized_email in {normalize_email(item.get("user", "")), normalize_email(item.get("friend", ""))}
        ],
        "follows": [
            item for item in social_data.get("follows", [])
            if isinstance(item, dict)
            and normalized_email in {normalize_email(item.get("follower", "")), normalize_email(item.get("following", ""))}
        ],
        "friend_requests": [
            item for item in social_data.get("friend_requests", [])
            if isinstance(item, dict)
            and normalized_email in {normalize_email(item.get("from", "")), normalize_email(item.get("to", ""))}
        ],
    }


def relationship_snapshot_for_email(data, key, email):
    normalized_email = normalize_email(email)
    relationships = data.get(key, {}) if isinstance(data, dict) else {}
    if not isinstance(relationships, dict):
        return {key: {}}

    snapshot = {}
    for owner, targets in relationships.items():
        owner_email = normalize_email(owner)
        target_list = targets if isinstance(targets, list) else []
        matched_targets = [target for target in target_list if normalize_email(target) == normalized_email]
        if owner_email == normalized_email:
            snapshot[owner_email] = target_list
        elif matched_targets:
            snapshot[owner_email] = matched_targets
    return {key: snapshot}


def clean_relationship_map(data, key, email):
    normalized_email = normalize_email(email)
    relationships = data.get(key, {}) if isinstance(data, dict) else {}
    if not isinstance(relationships, dict):
        return {key: {}}

    cleaned = {}
    for owner, targets in relationships.items():
        owner_email = normalize_email(owner)
        if owner_email == normalized_email:
            continue
        cleaned[owner_email] = [
            target for target in targets if normalize_email(target) != normalized_email
        ] if isinstance(targets, list) else []
    return {key: cleaned}


def record_involves_email(record, email, fields):
    normalized_email = normalize_email(email)
    if not isinstance(record, dict):
        return False

    return normalized_email in {
        normalize_email(record.get(field, ""))
        for field in fields
    }
