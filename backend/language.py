import json


DEFAULT_LANGUAGE = "en"


def load_languages():
    with open("database/language_data.json", "r", encoding="utf-8") as file:
        return json.load(file)


def detect_language(accept_language_header):
    if not accept_language_header:
        return DEFAULT_LANGUAGE

    header = accept_language_header.lower()

    if header.startswith("ru"):
        return "ru"

    if header.startswith("de"):
        return "de"

    if header.startswith("tr"):
        return "tr"

    if header.startswith("en"):
        return "en"

    return DEFAULT_LANGUAGE


def get_translations(accept_language_header):
    languages = load_languages()
    lang = detect_language(accept_language_header)

    return languages.get(lang, languages[DEFAULT_LANGUAGE])