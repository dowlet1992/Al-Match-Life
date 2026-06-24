import json


def normalize_email(email):
    return email.strip().lower()


def load_social(filename="social.json"):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
    except:
        data = {}

    if "friends" not in data:
        data["friends"] = []

    if "follows" not in data:
        data["follows"] = []

    if "friend_requests" not in data:
        data["friend_requests"] = []

    return data


def save_social(data, filename="social.json"):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def follow_user(follower_email, following_email):
    follower_email = normalize_email(follower_email)
    following_email = normalize_email(following_email)

    if follower_email == following_email:
        return False

    data = load_social()

    follow = {
        "follower": follower_email,
        "following": following_email
    }

    if follow not in data["follows"]:
        data["follows"].append(follow)
        save_social(data)
        return True

    return False


def unfollow_user(follower_email, following_email):
    follower_email = normalize_email(follower_email)
    following_email = normalize_email(following_email)

    data = load_social()

    follow = {
        "follower": follower_email,
        "following": following_email
    }

    if follow in data["follows"]:
        data["follows"].remove(follow)
        save_social(data)
        return True

    return False


def is_following(follower_email, following_email):
    follower_email = normalize_email(follower_email)
    following_email = normalize_email(following_email)

    data = load_social()

    return {
        "follower": follower_email,
        "following": following_email
    } in data["follows"]


def send_friend_request(sender_email, receiver_email):
    sender_email = normalize_email(sender_email)
    receiver_email = normalize_email(receiver_email)

    if sender_email == receiver_email:
        return False

    if are_friends(sender_email, receiver_email):
        return False

    data = load_social()

    request_item = {
        "from": sender_email,
        "to": receiver_email
    }

    if request_item not in data["friend_requests"]:
        data["friend_requests"].append(request_item)
        save_social(data)
        return True

    return False


def accept_friend_request(receiver_email, sender_email):
    receiver_email = normalize_email(receiver_email)
    sender_email = normalize_email(sender_email)

    data = load_social()

    request_item = {
        "from": sender_email,
        "to": receiver_email
    }

    if request_item in data["friend_requests"]:
        data["friend_requests"].remove(request_item)

        friendship = {
            "user": receiver_email,
            "friend": sender_email
        }

        reverse_friendship = {
            "user": sender_email,
            "friend": receiver_email
        }

        if friendship not in data["friends"] and reverse_friendship not in data["friends"]:
            data["friends"].append(friendship)

        save_social(data)
        return True

    return False


def remove_friend(user_email, friend_email):
    user_email = normalize_email(user_email)
    friend_email = normalize_email(friend_email)

    data = load_social()

    friendship = {
        "user": user_email,
        "friend": friend_email
    }

    reverse_friendship = {
        "user": friend_email,
        "friend": user_email
    }

    if friendship in data["friends"]:
        data["friends"].remove(friendship)

    if reverse_friendship in data["friends"]:
        data["friends"].remove(reverse_friendship)

    save_social(data)


def are_friends(user_email, friend_email):
    user_email = normalize_email(user_email)
    friend_email = normalize_email(friend_email)

    data = load_social()

    friendship = {
        "user": user_email,
        "friend": friend_email
    }

    reverse_friendship = {
        "user": friend_email,
        "friend": user_email
    }

    return friendship in data["friends"] or reverse_friendship in data["friends"]


def has_friend_request(sender_email, receiver_email):
    sender_email = normalize_email(sender_email)
    receiver_email = normalize_email(receiver_email)

    data = load_social()

    return {
        "from": sender_email,
        "to": receiver_email
    } in data["friend_requests"]


def count_friends(user_email):
    user_email = normalize_email(user_email)
    data = load_social()

    count = 0

    for item in data["friends"]:
        if normalize_email(item["user"]) == user_email or normalize_email(item["friend"]) == user_email:
            count += 1

    return count


def count_followers(user_email):
    user_email = normalize_email(user_email)
    data = load_social()

    count = 0

    for item in data["follows"]:
        if normalize_email(item["following"]) == user_email:
            count += 1

    return count


def count_following(user_email):
    user_email = normalize_email(user_email)
    data = load_social()

    count = 0

    for item in data["follows"]:
        if normalize_email(item["follower"]) == user_email:
            count += 1

    return count

def get_friends(user_email):
    user_email = normalize_email(user_email)
    data = load_social()
    result = []

    for item in data["friends"]:
        user = normalize_email(item["user"])
        friend = normalize_email(item["friend"])

        if user == user_email:
            result.append(friend)

        if friend == user_email:
            result.append(user)

    return result


def get_followers(user_email):
    user_email = normalize_email(user_email)
    data = load_social()
    result = []

    for item in data["follows"]:
        if normalize_email(item["following"]) == user_email:
            result.append(normalize_email(item["follower"]))

    return result


def get_following(user_email):
    user_email = normalize_email(user_email)
    data = load_social()
    result = []

    for item in data["follows"]:
        if normalize_email(item["follower"]) == user_email:
            result.append(normalize_email(item["following"]))

    return result

def get_friend_requests(email):
    email = normalize_email(email)

    data = load_social()

    requests = []

    for request in data["friend_requests"]:
        if normalize_email(request["to"]) == email:
            requests.append(request)

    return requests

def accept_friend_request(from_email, to_email):
    data = load_social()

    request = {
        "from": normalize_email(from_email),
        "to": normalize_email(to_email)
    }

    if request in data["friend_requests"]:

        data["friend_requests"].remove(request)

        data["friends"].append({
            "user": normalize_email(from_email),
            "friend": normalize_email(to_email)
        })

        save_social(data)

        return True

    return False

def decline_friend_request(from_email, to_email):
    data = load_social()

    request = {
        "from": normalize_email(from_email),
        "to": normalize_email(to_email)
    }

    if request in data["friend_requests"]:
        data["friend_requests"].remove(request)
        save_social(data)
        return True

    return False