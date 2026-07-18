from backend.repositories.user_repository import get_user_repository


def save_users_to_json(users, filename="users.json"):
    get_user_repository(filename).save_all(users)


def load_users_from_json(filename="users.json"):
    return get_user_repository(filename).load_all()
