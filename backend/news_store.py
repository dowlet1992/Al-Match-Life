from backend.repositories.news_repository import get_news_repository


def load_news():
    return get_news_repository().load_all()


def save_news(news_items, limit=500):
    get_news_repository().save_all(news_items, limit=limit)
