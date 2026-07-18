from backend.repositories.user_ai_settings_repository import get_user_ai_settings_repository


def load_user_ai_settings(email):
    return get_user_ai_settings_repository().load_for_email(email)


def save_user_ai_settings(email, settings):
    get_user_ai_settings_repository().save_for_email(email, settings)
