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


def analyze_user_profile(user):
    name = clean_text(user.name)
    profession = clean_text(user.profession)
    looking_for = clean_text(user.looking_for)
    skills = clean_list(user.skills)
    goals = clean_list(user.goals)
    interests = clean_list(user.interests)

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
        "interests": interests
    }


def explain_user_match(current_user, other_user):
    reasons = []

    current_goals = set(clean_list(current_user.goals))
    other_goals = set(clean_list(other_user.goals))

    current_interests = set(clean_list(current_user.interests))
    other_interests = set(clean_list(other_user.interests))

    current_skills = set(clean_list(current_user.skills))
    other_skills = set(clean_list(other_user.skills))

    common_goals = current_goals & other_goals
    common_interests = current_interests & other_interests
    common_skills = current_skills & other_skills

    if common_goals:
        reasons.append("Есть общие цели: " + ", ".join(list(common_goals)[:3]) + ".")

    if common_interests:
        reasons.append("Есть общие интересы: " + ", ".join(list(common_interests)[:3]) + ".")

    if common_skills:
        reasons.append("Есть похожие навыки: " + ", ".join(list(common_skills)[:3]) + ".")

    if clean_text(current_user.looking_for) != "не указано" and clean_text(other_user.profession) != "не указано":
        reasons.append("Профиль может быть полезен по направлению поиска.")

    if not reasons:
        reasons.append("AI пока не нашёл сильных совпадений, но профиль можно изучить вручную.")

    return reasons


def generate_feed_idea(user):
    name = clean_text(user.name)
    looking_for = clean_text(user.looking_for)

    if looking_for != "не указано":
        return f"{name}, можно опубликовать пост о том, кого вы ищете: {looking_for}."

    return f"{name}, можно опубликовать пост о ваших целях, проектах или поиске партнёров."


def analyze_proof_profile(proof_score):
    if proof_score >= 80:
        return "Сильный Proof Profile. Высокий уровень доверия."

    if proof_score >= 40:
        return "Средний Proof Profile. Нужно добавить больше доказательств."

    return "Proof Profile пока слабый. Добавьте проекты, сертификаты или видео-доказательства."

def generate_life_radar(user):
    return [
        "Посмотреть инвесторов",
        "Найти разработчиков",
        "Изучить новые стартапы"
    ]
