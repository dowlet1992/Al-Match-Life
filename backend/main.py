from database.users_data import users
from backend.models import User
from backend.recommendations import find_best_matches
from backend.explanations import explain_match
from backend.search import find_user_by_name, find_user_by_email_and_password, search_users
from backend.match_level import get_match_level
from backend.storage import save_users_to_json, load_users_from_json
from backend.trust import calculate_trust_score

def print_user(user):
    print("Name:", user.name)
    print("Age:", user.age)
    print("Email:", user.email)
    print("Country:", user.country)
    print("Bio:", user.bio)

    print("Languages:", ", ".join(user.languages))
    print("Goals:", ", ".join(user.goals))
    print("Interests:", ", ".join(user.interests))
    print("Skills:", ", ".join(user.skills))

    print("Trust Score:", user.trust_score)

    if user.verified:
        print("Verified: YES")
    else:
        print("Verified: NO")

    print("Profile Completed:", user.profile_completed)

    print("--------------------")


def show_matches(target_user, users):
    matches = find_best_matches(target_user, users)

    print("AI Match Life")
    print("TOP 5 MATCHES FOR:", target_user.name)
    print("====================")

    for index, match in enumerate(matches, start=1):
        matched_user = match["user"]
        reasons = explain_match(target_user, matched_user)
        level = get_match_level(match["score"])

        print(f"{index}. {matched_user.name} - {match['score']}")
        print("Age:", matched_user.age)
        print("Country:", matched_user.country)
        print("Bio:", matched_user.bio)
        print("Languages:", ", ".join(matched_user.languages))
        print("Match Level:", level)
        print("Reasons:")

        for reason in reasons:
            print("-", reason)

        print("----------------------")


def edit_profile(current_user, users):
    print("Edit Profile")
    print("Leave empty if you do not want to change something.")

    new_name = input("New name: ")
    new_country = input("New country: ")
    new_bio = input("New bio: ")
    new_languages = input("New languages, separated by comma: ")
    new_goals = input("New goals, separated by comma: ")
    new_interests = input("New interests, separated by comma: ")
    new_skills = input("New skills, separated by comma: ")

    if new_name != "":
        current_user.name = new_name

    if new_country != "":
        current_user.country = new_country

    if new_bio != "":
        current_user.bio = new_bio

    if new_languages != "":
        current_user.languages = [item.strip() for item in new_languages.split(",")]

    if new_goals != "":
        current_user.goals = [item.strip() for item in new_goals.split(",")]

    if new_interests != "":
        current_user.interests = [item.strip() for item in new_interests.split(",")]

    if new_skills != "":
        current_user.skills = [item.strip() for item in new_skills.split(",")]
    calculate_trust_score(current_user)
    save_users_to_json(users)

    print("Profile updated successfully.")
    print_user(current_user)


def user_menu(current_user, users):
    while True:
        print("")
        print("AI Match Life User Menu")
        print("1. My profile")
        print("2. Find my matches")
        print("3. Search people")
        print("4. Edit profile")
        print("5. Logout")
        print("6. Verify profile")
        choice = input("Choose option: ")

        if choice == "1":
            print_user(current_user)

        elif choice == "2":
            show_matches(current_user, users)

        elif choice == "3":
            keyword = input("Enter search keyword: ")
            results = search_users(users, keyword)

            print("AI Match Life Search")
            print("RESULTS FOR:", keyword)
            print("====================")

            for user in results:
                print_user(user)

        elif choice == "4":
            edit_profile(current_user, users)

        elif choice == "5":
            print("Logged out")
            break

        else:
            print("Wrong option")


loaded_users = load_users_from_json()
if loaded_users is not None:
    users = loaded_users


mode = input("Choose mode - login, match, search, language, country, role or register: ")

if mode == "login":
    email = input("Email: ")
    password = input("Password: ")

    user = find_user_by_email_and_password(users, email, password)

    if user is None:
        print("Wrong email or password")
    else:
        print("Welcome,", user.name)
        user_menu(user, users)

elif mode == "register":
    name = input("Name: ")
    age = int(input("Age: "))
    email = input("Email: ")
    password = input("Password: ")
    country = input("Country: ")
    bio = input("Bio: ")

    languages = input("Languages, separated by comma: ").split(",")
    goals = input("Goals, separated by comma: ").split(",")
    interests = input("Interests, separated by comma: ").split(",")
    skills = input("Skills, separated by comma: ").split(",")

    new_user = User(
        name,
        age,
        email,
        password,
        country,
        bio,
        [item.strip() for item in languages],
        [item.strip() for item in goals],
        [item.strip() for item in interests],
        [item.strip() for item in skills]
    )

    users.append(new_user)
    save_users_to_json(users)

    print("New user registered:")
    print_user(new_user)

elif mode == "search":
    keyword = input("Enter search keyword: ")
    results = search_users(users, keyword)

    print("AI Match Life Search")
    print("RESULTS FOR:", keyword)
    print("====================")

    for user in results:
        print_user(user)

elif mode == "language":
    language = input("Enter language: ").lower()

    print("AI Match Life Language Search")
    print("RESULTS FOR LANGUAGE:", language)
    print("====================")

    for user in users:
        if language in [lang.lower() for lang in user.languages]:
            print_user(user)

elif mode == "country":
    country = input("Enter country: ").lower()

    print("AI Match Life Country Search")
    print("RESULTS FOR COUNTRY:", country)
    print("====================")

    for user in users:
        if user.country.lower() == country:
            print_user(user)

elif mode == "role":
    role = input("Enter role - founder, developer, investor, marketing, product, designer: ")
    results = search_users(users, role)

    print("AI Match Life Role Search")
    print("RESULTS FOR ROLE:", role)
    print("====================")

    for user in results:
        print_user(user)

else:
    name = input("Enter user name: ")
    target_user = find_user_by_name(users, name)

    if target_user is None:
        print("User not found")
        exit()

    show_matches(target_user, users)