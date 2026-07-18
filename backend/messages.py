from backend.repositories.message_repository import get_message_repository


def load_messages():
    return get_message_repository().load_all()


def save_messages(messages):
    get_message_repository().save_all(messages)
