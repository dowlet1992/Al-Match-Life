def calculate_trust_score(user):
    score = 0

    if user.email:
        score += 20

    if user.bio:
        score += 15

    if user.languages:
        score += 15

    if user.goals:
        score += 15

    if user.interests:
        score += 15

    if user.skills:
        score += 15

    if user.verified:
        score += 5

    if score >= 80:
        user.profile_completed = True
    else:
        user.profile_completed = False

    user.trust_score = score
    return score