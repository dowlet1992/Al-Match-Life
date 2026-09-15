from backend.models import User
from backend.recommendations import find_best_matches


def make_user(email, *, goals=None, interests=None, skills=None, languages=None, country="Germany", profession="", looking_for="", trust=0):
    user = User("Person", 30, email, "hashed", country, "Bio", profession, looking_for, languages or [], goals or [], interests or [], skills or [])
    user.trust_score = trust
    return user


def test_radar_ranking_is_deterministic_and_explainable():
    current = make_user("current@example.com", goals=["startup"], interests=["AI"], skills=["product"], languages=["English"], looking_for="developer")
    strong = make_user("strong@example.com", goals=["startup"], interests=["AI"], skills=["product"], languages=["English"], profession="developer", trust=80)
    weak = make_user("weak@example.com", interests=["travel"], trust=20)

    matches = find_best_matches(current, [weak, strong, current])

    assert [item["user"].email for item in matches] == ["strong@example.com", "weak@example.com"]
    assert matches[0]["confidence"] == "high"
    assert matches[0]["signals"]["shared_goals"] > 0
    assert matches[0]["signals"]["intent_fit"] > 0
    assert matches[0]["signal_details"]["shared_interests"] == ["ai"]


def test_radar_uses_trust_only_as_small_tie_breaking_signal():
    current = make_user("current@example.com", interests=["AI"], country="")
    relevant = make_user("relevant@example.com", interests=["AI"], country="", trust=5)
    trusted_but_irrelevant = make_user("trusted@example.com", interests=["Cooking"], country="", trust=100)

    matches = find_best_matches(current, [trusted_but_irrelevant, relevant])

    assert matches[0]["user"].email == "relevant@example.com"
    assert len(matches) == 1


def test_radar_confidence_uses_actual_matches_not_just_filled_fields():
    current = make_user(
        "current@example.com", goals=["startup"], interests=["AI"],
        skills=["product"], languages=["English"], country="Germany",
    )
    unrelated = make_user(
        "other@example.com", goals=["fitness"], interests=["cooking"],
        skills=["accounting"], languages=["Spanish"], country="Germany",
    )

    match = find_best_matches(current, [unrelated])[0]

    assert match["confidence"] == "low"
    assert set(match["signals"]) >= {"same_country", "profile_quality"}


def test_radar_intent_matching_uses_whole_words_and_accepts_specific_roles():
    current = make_user("current@example.com", country="", looking_for="art")
    false_positive = make_user("false@example.com", country="", profession="partner")
    developer_search = make_user("search@example.com", country="", looking_for="software developer")
    senior_developer = make_user("senior@example.com", country="", profession="senior software developer")

    assert find_best_matches(current, [false_positive]) == []
    matches = find_best_matches(developer_search, [senior_developer])
    assert matches[0]["signals"]["intent_fit"] > 0


def test_radar_accepts_legacy_comma_separated_profile_terms():
    current = make_user("current@example.com", interests="AI, Travel", country="")
    candidate = make_user("candidate@example.com", interests=["AI"], country="")

    match = find_best_matches(current, [candidate])[0]

    assert match["signal_details"]["shared_interests"] == ["ai"]
