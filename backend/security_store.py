from backend.repositories.security_repository import get_security_repository


def load_login_attempts():
    return get_security_repository().load_login_attempts()


def save_login_attempts(data):
    get_security_repository().save_login_attempts(data)


def load_security_events():
    return get_security_repository().load_security_events()


def append_security_event(event, limit=1000):
    events = load_security_events()
    if not isinstance(event, dict):
        return

    events.append(event)
    get_security_repository().save_security_events(events[-limit:])
