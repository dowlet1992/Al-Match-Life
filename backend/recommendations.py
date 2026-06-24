from backend.matching import calculate_match_score
from backend.privacy import get_user_privacy


def find_best_matches(current_user, users):
    matches = []

    current_goals = set([x.strip().lower() for x in current_user.goals if x.strip()])
    current_interests = set([x.strip().lower() for x in current_user.interests if x.strip()])
    current_skills = set([x.strip().lower() for x in current_user.skills if x.strip()])
    current_languages = set([x.strip().lower() for x in current_user.languages if x.strip()])
    current_country = str(current_user.country).strip().lower()
    current_looking_for = str(current_user.looking_for).strip().lower()
    current_profession = str(current_user.profession).strip().lower()

    for user in users:
        if user.email.strip().lower() == current_user.email.strip().lower():
            continue

        user_goals = set([x.strip().lower() for x in user.goals if x.strip()])
        user_interests = set([x.strip().lower() for x in user.interests if x.strip()])
        user_skills = set([x.strip().lower() for x in user.skills if x.strip()])
        user_languages = set([x.strip().lower() for x in user.languages if x.strip()])
        user_country = str(user.country).strip().lower()
        user_looking_for = str(user.looking_for).strip().lower()
        user_profession = str(user.profession).strip().lower()

        score = 0

        if current_goals and user_goals:
            goal_match = len(current_goals.intersection(user_goals)) / len(current_goals.union(user_goals))
            score += goal_match * 30

        if current_interests and user_interests:
            interest_match = len(current_interests.intersection(user_interests)) / len(current_interests.union(user_interests))
            score += interest_match * 20

        if current_skills and user_skills:
            skill_match = len(current_skills.intersection(user_skills)) / len(current_skills.union(user_skills))
            score += skill_match * 15

        if current_languages and user_languages:
            language_match = len(current_languages.intersection(user_languages)) / len(current_languages.union(user_languages))
            score += language_match * 15

        if current_country and user_country and current_country == user_country:
            score += 10

        if current_looking_for and user_profession:
            if current_looking_for in user_profession or user_profession in current_looking_for:
                score += 5

        if current_profession and user_looking_for:
            if current_profession in user_looking_for or user_looking_for in current_profession:
                score += 5

        final_score = round(min(score, 100))

        if final_score > 0:
            matches.append({
                "user": user,
                "score": final_score
            })

    matches.sort(key=lambda item: item["score"], reverse=True)

    return matches