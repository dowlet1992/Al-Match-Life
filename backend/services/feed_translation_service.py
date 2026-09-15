def generate_ai_translation_summary(text_value, source_language, target_language, deps):
    text_value = deps["clean_text"](text_value)
    source_language = deps["normalize_content_language_code"](source_language)
    target_language = deps["normalize_content_language_code"](target_language)

    if not text_value:
        return "Текст для перевода не найден."

    source_language_name = deps["content_languages"]().get(source_language, source_language)
    target_language_name = deps["content_languages"]().get(target_language, target_language)

    if not deps["provider_available"]():
        return (
            "AI-перевод пока недоступен: локальная AI-модель не подключена. "
            f"Оригинальный язык: {source_language_name}. Целевой язык: {target_language_name}."
        )

    prompt = (
        "You are an accurate multilingual assistant for a social network feed. "
        "Translate the post into the target language and add a short useful summary. "
        "Keep the meaning. Do not add false facts. Do not advertise anything.\n\n"
        f"Source language: {source_language_name}\n"
        f"Target language: {target_language_name}\n\n"
        f"Post text:\n{text_value}\n\n"
        "Return in this format:\n"
        "Translation:\n...\n\nShort summary:\n..."
    )

    try:
        result = deps["chat"](
            [
            {"role": "system", "content": "You translate and summarize social feed posts accurately."},
            {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=700,
            strict=True,
        )
        return deps["clean_text"](result) or "AI-перевод временно недоступен. Попробуйте позже."
    except Exception as error:
        deps["log_security_event"]("ai_translation_failed", deps["current_session_email"](), str(error))
        return "AI-перевод временно недоступен. Попробуйте позже."
