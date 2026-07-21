def normalize_language(value, normalizer):
    language = normalizer(value)
    return language if language and language != "unknown" else "unknown"


def cached_translation(message, target_language, normalizer):
    target_language = normalize_language(target_language, normalizer)
    translations = message.get("translations", {})
    if not isinstance(translations, dict):
        return ""
    return str(translations.get(target_language, "")).strip()


def translate_message(message, target_language, normalizer, translate_text):
    target_language = normalize_language(target_language, normalizer)
    if target_language == "unknown":
        return {"ok": False, "error": "unsupported_target_language"}

    text = str(message.get("message", "")).strip()
    if not text:
        return {"ok": False, "error": "message_has_no_text"}

    source_language = normalize_language(message.get("source_language"), normalizer)
    if source_language == target_language:
        return {
            "ok": True,
            "translated_text": text,
            "source_language": source_language,
            "target_language": target_language,
            "cached": True,
        }

    cached = cached_translation(message, target_language, normalizer)
    if cached:
        return {
            "ok": True,
            "translated_text": cached,
            "source_language": source_language,
            "target_language": target_language,
            "cached": True,
        }

    translated_text = str(translate_text(text, source_language, target_language) or "").strip()
    if not translated_text:
        return {"ok": False, "error": "translation_unavailable"}

    translations = message.get("translations", {})
    if not isinstance(translations, dict):
        translations = {}
    translations[target_language] = translated_text
    message["translations"] = translations
    return {
        "ok": True,
        "translated_text": translated_text,
        "source_language": source_language,
        "target_language": target_language,
        "cached": False,
    }


def auto_translate_incoming(messages, current_email, target_language, normalizer, translate_text, limit=20):
    current_email = str(current_email or "").strip().lower()
    changed = 0
    results = {}
    for message in list(messages or [])[-max(int(limit or 0), 0):]:
        if not isinstance(message, dict) or str(message.get("to", "")).strip().lower() != current_email:
            continue
        result = translate_message(message, target_language, normalizer, translate_text)
        if result.get("ok"):
            results[str(message.get("id", ""))] = result
            if not result.get("cached"):
                changed += 1
    return {"changed": changed, "results": results}
