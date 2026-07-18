from backend.repositories.stories_repository import get_stories_repository, normalize_stories_data


def load_stories():
    return get_stories_repository().load_all()


def save_stories(data):
    get_stories_repository().save_all(normalize_stories_data(data))
