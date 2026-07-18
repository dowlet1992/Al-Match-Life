from backend.repositories.social_safety_repository import (
    get_blocks_repository,
    get_hidden_stories_repository,
    get_reports_repository,
    get_restrictions_repository,
)


def load_blocks():
    return get_blocks_repository().load_all()


def save_blocks(data):
    get_blocks_repository().save_all(data)


def load_reports():
    return get_reports_repository().load_all()


def save_reports(data):
    get_reports_repository().save_all(data)


def load_restrictions():
    return get_restrictions_repository().load_all()


def save_restrictions(data):
    get_restrictions_repository().save_all(data)


def load_hidden_stories():
    return get_hidden_stories_repository().load_all()


def save_hidden_stories(data):
    get_hidden_stories_repository().save_all(data)
