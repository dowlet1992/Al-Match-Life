
import json
import os
import urllib.error
import urllib.request


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def clean_text(value):
    if value is None:
        return "не указано"

    value = str(value).strip()

    if value == "":
        return "не указано"

    return value


def clean_list(values):
    if values is None:
        return []

    if isinstance(values, list):
        return [str(item).strip() for item in values if str(item).strip() != ""]

    return [str(values).strip()] if str(values).strip() != "" else []


def _safe_get(user, field_name, default=""):
    return getattr(user, field_name, default)


def _user_snapshot(user):
    return {
        "name": clean_text(_safe_get(user, "name")),
        "email": clean_text(_safe_get(user, "email")),
        "profession": clean_text(_safe_get(user, "profession")),
        "looking_for": clean_text(_safe_get(user, "looking_for")),
        "bio": clean_text(_safe_get(user, "bio")),
        "location": clean_text(_safe_get(user, "location")),
        "country": clean_text(_safe_get(user, "country")),
        "city": clean_text(_safe_get(user, "city")),
        "skills": clean_list(_safe_get(user, "skills")),
        "goals": clean_list(_safe_get(user, "goals")),
        "interests": clean_list(_safe_get(user, "interests")),
        "languages": clean_list(_safe_get(user, "languages")),
    }


def _fallback_profile_analysis(user):
    name = clean_text(_safe_get(user, "name"))
    profession = clean_text(_safe_get(user, "profession"))
    looking_for = clean_text(_safe_get(user, "looking_for"))
    skills = clean_list(_safe_get(user, "skills"))
    goals = clean_list(_safe_get(user, "goals"))
    interests = clean_list(_safe_get(user, "interests"))

    summary_parts = []
    summary_parts.append(f"{name} использует AI Match Life для поиска полезных людей и возможностей.")

    if looking_for != "не указано":
        summary_parts.append(f"Основной запрос: {looking_for}.")

    if profession != "не указано":
        summary_parts.append(f"Профессиональное направление: {profession}.")

    if goals:
        summary_parts.append("Цели: " + ", ".join(goals[:3]) + ".")

    if skills:
        summary_parts.append("Сильные стороны: " + ", ".join(skills[:3]) + ".")

    if interests:
        summary_parts.append("Интересы: " + ", ".join(interests[:3]) + ".")

    if looking_for == "не указано" and profession == "не указано" and not goals and not skills and not interests:
        summary_parts.append("Профиль пока заполнен слабо. Чем больше данных пользователь добавит, тем точнее AI сможет рекомендовать людей.")

    return {
        "summary": " ".join(summary_parts),
        "strengths": skills,
        "goals": goals,
        "interests": interests,
        "ai_enabled": False,
    }


def _fallback_match_explanation(current_user, other_user):
    reasons = []

    current_goals = set(clean_list(_safe_get(current_user, "goals")))
    other_goals = set(clean_list(_safe_get(other_user, "goals")))

    current_interests = set(clean_list(_safe_get(current_user, "interests")))
    other_interests = set(clean_list(_safe_get(other_user, "interests")))

    current_skills = set(clean_list(_safe_get(current_user, "skills")))
    other_skills = set(clean_list(_safe_get(other_user, "skills")))

    common_goals = current_goals & other_goals
    common_interests = current_interests & other_interests
    common_skills = current_skills & other_skills

    if common_goals:
        reasons.append("Есть общие цели: " + ", ".join(list(common_goals)[:3]) + ".")

    if common_interests:
        reasons.append("Есть общие интересы: " + ", ".join(list(common_interests)[:3]) + ".")

    if common_skills:
        reasons.append("Есть похожие навыки: " + ", ".join(list(common_skills)[:3]) + ".")

    if clean_text(_safe_get(current_user, "looking_for")) != "не указано" and clean_text(_safe_get(other_user, "profession")) != "не указано":
        reasons.append("Профиль может быть полезен по направлению поиска.")

    if not reasons:
        reasons.append("AI пока не нашёл сильных совпадений, но профиль можно изучить вручную.")

    return reasons


def _call_openai(messages, temperature=0.35, max_tokens=700):
    if not OPENAI_API_KEY:
        return ""

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, IndexError, json.JSONDecodeError):
        return ""


def _extract_json_object(text):
    if not text:
        return None

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None


def _extract_json_array(text):
    if not text:
        return None

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        value = json.loads(cleaned)
        return value if isinstance(value, list) else None
    except json.JSONDecodeError:
        pass

    start = cleaned.find("[")
    end = cleaned.rfind("]")

    if start == -1 or end == -1 or end <= start:
        return None

    try:
        value = json.loads(cleaned[start:end + 1])
        return value if isinstance(value, list) else None
    except json.JSONDecodeError:
        return None


def analyze_user_profile(user):
    fallback = _fallback_profile_analysis(user)
    snapshot = _user_snapshot(user)

    prompt = f"""
Ты — AI Match Life intelligence engine.
Твоя задача — профессионально проанализировать профиль пользователя для платформы знакомств, бизнеса, дружбы, целей и развития.

Важно:
- отвечай только на русском языке;
- не выдумывай факты;
- если данных мало, честно скажи, что профиль нужно заполнить лучше;
- стиль должен быть премиальный, конкретный, без воды;
- верни только JSON без markdown.

Данные пользователя:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}

Верни JSON строго в таком формате:
{{
  "summary": "короткий профессиональный анализ профиля в 2-4 предложениях",
  "strengths": ["сила 1", "сила 2", "сила 3"],
  "goals": ["цель 1", "цель 2", "цель 3"],
  "interests": ["интерес 1", "интерес 2", "интерес 3"],
  "profile_quality": "слабый | средний | сильный",
  "improvement_tips": ["совет 1", "совет 2", "совет 3"]
}}
"""

    response = _call_openai(
        [
            {"role": "system", "content": "Ты точный AI-анализатор профилей для AI Match Life. Возвращай только валидный JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.28,
        max_tokens=900,
    )

    data = _extract_json_object(response)

    if not isinstance(data, dict):
        return fallback

    return {
        "summary": clean_text(data.get("summary")) if clean_text(data.get("summary")) != "не указано" else fallback["summary"],
        "strengths": clean_list(data.get("strengths")) or fallback["strengths"],
        "goals": clean_list(data.get("goals")) or fallback["goals"],
        "interests": clean_list(data.get("interests")) or fallback["interests"],
        "profile_quality": clean_text(data.get("profile_quality")),
        "improvement_tips": clean_list(data.get("improvement_tips")),
        "ai_enabled": True,
    }


def explain_user_match(current_user, other_user):
    fallback = _fallback_match_explanation(current_user, other_user)

    current_snapshot = _user_snapshot(current_user)
    other_snapshot = _user_snapshot(other_user)

    prompt = f"""
Ты — AI Match Life matching engine.
Нужно объяснить, почему два пользователя могут быть полезны друг другу для бизнеса, дружбы, целей, развития или сотрудничества.

Важно:
- отвечай только на русском языке;
- не выдумывай факты;
- не пиши слишком длинно;
- объяснение должно быть человеческим и полезным;
- если совпадений мало, честно скажи, какие данные стоит добавить;
- верни только JSON-массив строк.

Текущий пользователь:
{json.dumps(current_snapshot, ensure_ascii=False, indent=2)}

Другой пользователь:
{json.dumps(other_snapshot, ensure_ascii=False, indent=2)}

Верни JSON-массив из 2-5 коротких причин.
"""

    response = _call_openai(
        [
            {"role": "system", "content": "Ты точный AI matching engine. Возвращай только валидный JSON-массив строк."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.32,
        max_tokens=600,
    )

    reasons = _extract_json_array(response)

    if not reasons:
        return fallback

    cleaned_reasons = [clean_text(reason) for reason in reasons if clean_text(reason) != "не указано"]
    return cleaned_reasons[:5] if cleaned_reasons else fallback


def generate_feed_idea(user):
    snapshot = _user_snapshot(user)
    fallback_name = snapshot["name"]
    fallback_looking_for = snapshot["looking_for"]

    fallback = (
        f"{fallback_name}, можно опубликовать пост о том, кого вы ищете: {fallback_looking_for}."
        if fallback_looking_for != "не указано"
        else f"{fallback_name}, можно опубликовать пост о ваших целях, проектах или поиске партнёров."
    )

    prompt = f"""
Ты — AI помощник для создания постов в AI Match Life.
Предложи одну конкретную идею поста, которая поможет пользователю найти полезных людей.

Требования:
- русский язык;
- 1-2 предложения;
- без хэштегов;
- без воды;
- не выдумывай факты.

Данные пользователя:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
"""

    response = _call_openai(
        [
            {"role": "system", "content": "Ты создаёшь короткие идеи постов для социальной AI-платформы."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.55,
        max_tokens=220,
    )

    return clean_text(response) if response else fallback


def analyze_proof_profile(proof_score):
    try:
        proof_score = int(proof_score)
    except (TypeError, ValueError):
        proof_score = 0

    if proof_score >= 80:
        return "Сильный Proof Profile. Высокий уровень доверия. Такой профиль можно активнее показывать в рекомендациях."

    if proof_score >= 40:
        return "Средний Proof Profile. Нужно добавить больше доказательств: проекты, опыт, сертификаты, видео или подтверждения."

    return "Proof Profile пока слабый. Добавьте проекты, сертификаты, ссылки, видео-доказательства или подтверждение личности."


def generate_life_radar(user):
    snapshot = _user_snapshot(user)
    fallback = [
        "Усилить профиль: добавить цели, навыки и конкретный запрос.",
        "Найти людей по профессии, интересам и общим целям.",
        "Добавить Proof Profile, чтобы повысить доверие.",
    ]

    prompt = f"""
Ты — AI Life Radar внутри AI Match Life.
На основе профиля пользователя предложи 3-5 практических направлений, которые помогут ему развиваться и находить полезных людей.

Требования:
- русский язык;
- коротко и конкретно;
- без мотивационной воды;
- не выдумывай факты;
- верни только JSON-массив строк.

Данные пользователя:
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
"""

    response = _call_openai(
        [
            {"role": "system", "content": "Ты практичный AI Life Radar. Возвращай только валидный JSON-массив строк."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
        max_tokens=500,
    )

    items = _extract_json_array(response)

    if not items:
        return fallback

    cleaned_items = [clean_text(item) for item in items if clean_text(item) != "не указано"]
    return cleaned_items[:5] if cleaned_items else fallback
