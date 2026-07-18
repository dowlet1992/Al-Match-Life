from backend.repositories.call_signal_repository import get_call_signal_repository


def load_call_signals():
    return get_call_signal_repository().load_all()


def save_call_signals(data):
    get_call_signal_repository().save_all(data)
