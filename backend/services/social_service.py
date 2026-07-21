from backend.social import (
    accept_friend_request,
    are_friends,
    decline_friend_request,
    follow_user,
    has_friend_request,
    is_following,
    load_social,
    send_friend_request,
    unfollow_user,
)


def normalize_email(value):
    return str(value or "").strip().lower()


def blocked_between(user_email, target_email, is_blocked):
    return is_blocked(user_email, target_email) or is_blocked(target_email, user_email)


def relationship_snapshot(current_user, target_user, social_data=None):
    current_email = normalize_email(current_user.email)
    target_email = normalize_email(target_user.email)
    social_data = social_data if isinstance(social_data, dict) else load_social()
    follows = {
        (normalize_email(item.get("follower")), normalize_email(item.get("following")))
        for item in social_data.get("follows", [])
        if isinstance(item, dict)
    }
    current_follows_target = current_email != target_email and (current_email, target_email) in follows
    target_follows_current = current_email != target_email and (target_email, current_email) in follows

    return {
        "is_self": current_email == target_email,
        "is_following": current_follows_target,
        "follows_you": target_follows_current,
        "is_mutual": current_follows_target and target_follows_current,
        "followers_count": sum(1 for follower, following in follows if following == target_email),
        "following_count": sum(1 for follower, following in follows if follower == target_email),
    }


def follow(current_user, target_user, is_blocked):
    current_email = normalize_email(current_user.email)
    target_email = normalize_email(target_user.email)

    if current_email == target_email:
        return {"ok": False, "error": "You cannot follow yourself", "status": 400}

    if blocked_between(current_email, target_email, is_blocked):
        return {"ok": False, "error": "Social action is not available for these users", "status": 403}

    changed = follow_user(current_email, target_email)
    return {
        "ok": True,
        "changed": changed,
        **relationship_snapshot(current_user, target_user),
    }


def unfollow(current_user, target_user):
    current_email = normalize_email(current_user.email)
    target_email = normalize_email(target_user.email)
    changed = unfollow_user(current_email, target_email)

    return {
        "ok": True,
        "changed": changed,
        **relationship_snapshot(current_user, target_user),
    }


def request_friend(current_user, target_user, is_blocked):
    current_email = normalize_email(current_user.email)
    target_email = normalize_email(target_user.email)

    if current_email == target_email:
        return {"ok": False, "error": "You cannot send a friend request to yourself", "status": 400}

    if blocked_between(current_email, target_email, is_blocked):
        return {"ok": False, "error": "Social action is not available for these users", "status": 403}

    changed = send_friend_request(current_email, target_email)
    return {
        "ok": True,
        "changed": changed,
        "friend_request_sent": has_friend_request(current_email, target_email),
        "are_friends": are_friends(current_email, target_email),
    }


def accept_request(current_user, target_user, is_blocked):
    current_email = normalize_email(current_user.email)
    target_email = normalize_email(target_user.email)

    if blocked_between(current_email, target_email, is_blocked):
        return {"ok": False, "error": "Social action is not available for these users", "status": 403}

    changed = accept_friend_request(current_email, target_email)
    return {
        "ok": True,
        "changed": changed,
        "are_friends": are_friends(current_email, target_email),
    }


def decline_request(current_user, target_user):
    current_email = normalize_email(current_user.email)
    target_email = normalize_email(target_user.email)
    changed = decline_friend_request(current_email, target_email)

    return {
        "ok": True,
        "changed": changed,
        "friend_request_sent": has_friend_request(target_email, current_email),
    }
