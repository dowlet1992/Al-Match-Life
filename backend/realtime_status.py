from backend.repositories.realtime_repository import get_realtime_repository


def load_typing_status():
    return get_realtime_repository().load_typing_status()


def save_typing_status(data):
    get_realtime_repository().save_typing_status(data)


def load_presence_status():
    return get_realtime_repository().load_presence_status()


def save_presence_status(data):
    get_realtime_repository().save_presence_status(data)
