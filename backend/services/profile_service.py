from backend.serializers import clean_text


def parse_short_list(value, limit=6):
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = str(value or "").replace(";", ",").split(",")

    result = []
    for item in raw_items:
        cleaned = clean_text(item).strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break

    return result


def user_needs_onboarding(user):
    if user is None:
        return False

    if getattr(user, "onboarding_completed", False) or getattr(user, "onboarding_skipped", False):
        return False

    signal_count = 0
    for field_name in ["looking_for", "profession"]:
        if clean_text(getattr(user, field_name, "")).strip():
            signal_count += 1

    for field_name in ["languages", "goals", "interests", "skills"]:
        values = getattr(user, field_name, []) or []
        if isinstance(values, list) and values:
            signal_count += 1

    return signal_count < 3


def update_profile(user, data, list_limit=12):
    for field_name in ["bio", "profession", "looking_for", "country"]:
        if field_name in data:
            setattr(user, field_name, clean_text(data.get(field_name, "")))

    for field_name in ["languages", "goals", "interests", "skills"]:
        if field_name in data:
            setattr(user, field_name, parse_short_list(data.get(field_name), limit=list_limit))

    return user


def apply_onboarding(user, data):
    if user is None:
        return False

    looking_for = clean_text(data.get("looking_for", ""))
    profession = clean_text(data.get("profession", ""))
    goals = parse_short_list(data.get("goals", ""))
    interests = parse_short_list(data.get("interests", ""))
    skills = parse_short_list(data.get("skills", ""))
    languages = parse_short_list(data.get("languages", ""))

    if looking_for:
        user.looking_for = looking_for
    if profession:
        user.profession = profession
    if goals:
        user.goals = goals
    if interests:
        user.interests = interests
    if skills:
        user.skills = skills
    if languages:
        user.languages = languages

    user.onboarding_completed = True
    user.onboarding_skipped = False
    return True


def skip_onboarding(user):
    user.onboarding_skipped = True
    user.onboarding_completed = False
    return user
