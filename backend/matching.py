def calculate_match_score(user1, user2):
    score = 0

    shared_goals = set(user1.goals) & set(user2.goals)
    shared_interests = set(user1.interests) & set(user2.interests)
    shared_skills = set(user1.skills) & set(user2.skills)

    score += len(shared_goals) * 50
    score += len(shared_interests) * 30
    score += len(shared_skills) * 20

    if user1.country == user2.country:
     score += 20
    shared_languages = set(user1.languages) & set(user2.languages)

    score += len(shared_languages) * 15
    age_difference = abs(user1.age - user2.age)

    if age_difference <= 3:
        score += 30
    elif age_difference <= 7:
        score += 20
    elif age_difference <= 12:
        score += 10

    complementary_skills = {
        "vision": ["programming", "product", "ai engineering"],
        "business thinking": ["programming", "product", "marketing"],
        "programming": ["vision", "business thinking", "sales"],
        "product": ["vision", "business thinking"],
        "marketing": ["vision", "business thinking", "programming"],
        "sales": ["product", "programming", "brand strategy"]
    }

    for skill in user1.skills:
        if skill in complementary_skills:
            for other_skill in user2.skills:
                if other_skill in complementary_skills[skill]:
                    score += 25

    return score


def find_best_matches(target_user, users):
    matches = []

    for user in users:
        if user.name == target_user.name:
            continue

        score = calculate_match_score(target_user, user)

        matches.append({
            "user": user,
            "score": score
        })

    matches.sort(key=lambda x: x["score"], reverse=True)

    return matches[:5]