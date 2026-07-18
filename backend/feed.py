from backend.repositories.feed_repository import get_feed_repository


def load_feed():
    return get_feed_repository().load_all()


def save_feed(data):
    get_feed_repository().save_all(data)
