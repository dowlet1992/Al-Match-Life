def get_match_level(score):
    if score >= 200:
        return "Excellent Match"

    if score >= 150:
        return "Strong Match"

    if score >= 100:
        return "Good Match"

    if score >= 50:
        return "Medium Match"

    return "Low Match"