def normalize_list(values):
    return set([str(item).strip().lower() for item in values if str(item).strip()])


def explain_match(user1, user2):
    reasons = []

    goals1 = normalize_list(user1.goals)
    goals2 = normalize_list(user2.goals)

    interests1 = normalize_list(user1.interests)
    interests2 = normalize_list(user2.interests)

    skills1 = normalize_list(user1.skills)
    skills2 = normalize_list(user2.skills)

    languages1 = normalize_list(user1.languages)
    languages2 = normalize_list(user2.languages)

    shared_goals = goals1.intersection(goals2)
    shared_interests = interests1.intersection(interests2)
    shared_skills = skills1.intersection(skills2)
    shared_languages = languages1.intersection(languages2)

    if shared_goals:
        reasons.append("✓ У вас совпадают цели: " + ", ".join(sorted(shared_goals)))

    if shared_interests:
        reasons.append("✓ Общие интересы: " + ", ".join(sorted(shared_interests)))

    if shared_skills:
        reasons.append("✓ Похожие навыки: " + ", ".join(sorted(shared_skills)))

    if shared_languages:
        reasons.append("✓ Вы можете общаться на общих языках: " + ", ".join(sorted(shared_languages)))

    if str(user1.country).strip().lower() == str(user2.country).strip().lower():
        reasons.append("✓ Вы находитесь в одной стране: " + str(user1.country))

    complementary_pairs = [
        ("vision", "programming", "один человек даёт видение, другой может помочь с разработкой"),
        ("business thinking", "programming", "бизнес-мышление хорошо дополняется техническими навыками"),
        ("business thinking", "marketing", "бизнес-мышление хорошо дополняется маркетингом"),
        ("product", "programming", "продуктовое мышление хорошо сочетается с разработкой"),
        ("branding", "sales", "брендинг хорошо дополняется продажами")
    ]

    for skill1, skill2, explanation in complementary_pairs:
        if skill1 in skills1 and skill2 in skills2:
            reasons.append("✓ Дополняющие навыки: " + explanation)

    if not reasons:
        reasons.append("✓ AI нашёл общий потенциал по профилю, целям и направлению развития.")

    return reasons