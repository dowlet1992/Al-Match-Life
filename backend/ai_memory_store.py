from backend.repositories.ai_memory_repository import get_ai_memory_repository


def load_ai_core_memory():
    return get_ai_memory_repository().load_core_memory()


def save_ai_core_memory(data):
    get_ai_memory_repository().save_core_memory(data)


def load_ai_feed_learning():
    return get_ai_memory_repository().load_feed_learning()


def save_ai_feed_learning(data):
    get_ai_memory_repository().save_feed_learning(data)
