from backend.repositories import JsonStore


_verification_codes_store = JsonStore("verification_codes.json", {})


def load_verification_codes():
    data = _verification_codes_store.load()
    if not isinstance(data, dict):
        return {}
    return data


def save_verification_codes(data):
    if not isinstance(data, dict):
        data = {}
    _verification_codes_store.save(data)
