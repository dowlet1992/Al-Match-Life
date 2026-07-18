import json
import os
import urllib.request


def generate_ai_translation_summary(text_value, source_language, target_language, deps):
    text_value = deps["clean_text"](text_value)
    source_language = deps["normalize_content_language_code"](source_language)
    target_language = deps["normalize_content_language_code"](target_language)

    if not text_value:
        return "Текст для перевода не найден."

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    source_language_name = deps["content_languages"]().get(source_language, source_language)
    target_language_name = deps["content_languages"]().get(target_language, target_language)

    if not openai_key.startswith("sk-"):
        return (
            "AI-перевод пока недоступен: OPENAI_API_KEY не подключён. "
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

    payload = {
        "model": openai_model,
        "messages": [
            {"role": "system", "content": "You translate and summarize social feed posts accurately."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }

    try:
        request_data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
            return deps["clean_text"](result["choices"][0]["message"]["content"])
    except Exception as error:
        deps["log_security_event"]("ai_translation_failed", deps["current_session_email"](), str(error))
        return "AI-перевод временно недоступен. Попробуйте позже."
