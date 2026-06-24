from backend.privacy import get_user_privacy


def find_user_by_name(users, name):
    for user in users:
        if user.name.lower() == name.lower():
            return user

    return None


def find_user_by_email_and_password(users, email, password):
    for user in users:
        if user.email == email and user.password == password:
            return user

    return None


def search_users(users, keyword):
    results = []
    keyword = keyword.lower()

    synonyms = {
        "investor": ["investor", "investment", "investing", "business advisor"],
        "developer": ["developer", "programming", "engineer", "ai engineering"],
        "founder": ["founder", "entrepreneur", "startup"],
        "marketing": ["marketing", "growth marketing", "communication"],
        "product": ["product", "product manager", "product engineer"],
        "designer": ["designer", "design", "ui ux", "branding"],
        "ai": ["ai", "artificial intelligence", "automation", "ai startup"]
    }

    search_words = synonyms.get(keyword, [keyword])

    for user in users:
        privacy = get_user_privacy(user.email)

        if privacy.get("show_in_search") == False:
            continue

        if privacy.get("vip_mode") == True:
            continue

        searchable_text = (
            user.name + " " +
            user.country + " " +
            user.bio + " " +
            user.profession + " " +
            user.looking_for + " " +
            " ".join(user.languages) + " " +
            " ".join(user.goals) + " " +
            " ".join(user.interests) + " " +
            " ".join(user.skills)
        ).lower()

        for word in search_words:
            if word in searchable_text:
                results.append(user)
                break

    return results