from backend.repositories import JsonStore
from backend.i18n import DEFAULT_LANGUAGE, detect_language


_language_store = JsonStore("database/language_data.json", {DEFAULT_LANGUAGE: {}})


def load_languages():
    data = _language_store.load()
    if not isinstance(data, dict):
        return {DEFAULT_LANGUAGE: {}}
    if DEFAULT_LANGUAGE not in data or not isinstance(data.get(DEFAULT_LANGUAGE), dict):
        data[DEFAULT_LANGUAGE] = {}
    return data


def get_translations(accept_language_header):
    languages = load_languages()
    lang = detect_language(accept_language_header)

    return languages.get(lang, languages[DEFAULT_LANGUAGE])
