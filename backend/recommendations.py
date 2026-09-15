"""Deterministic, explainable people recommendations for NOVIX Radar."""

import re


def _text(value):
    return str(value or "").strip().casefold()


def _terms(values):
    if isinstance(values, str):
        values = re.split(r"[,;\n]", values)
    return {_text(value) for value in (values or []) if _text(value)}


def _jaccard(left, right):
    union = left | right
    return (len(left & right) / len(union)) if union else 0.0


def _affinity(left, right):
    """Balance overall similarity with coverage of the smaller profile list."""
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    if not intersection:
        return 0.0
    overlap = intersection / min(len(left), len(right))
    return (_jaccard(left, right) + overlap) / 2


def _intent_match(looking_for, profession):
    if not looking_for or not profession:
        return False
    requested_terms = set(re.findall(r"[^\W_]+", looking_for, flags=re.UNICODE))
    profession_terms = set(re.findall(r"[^\W_]+", profession, flags=re.UNICODE))
    if not requested_terms or not profession_terms:
        return False
    return requested_terms <= profession_terms or profession_terms <= requested_terms


def _profile_completeness(user):
    values = (
        getattr(user, "profession", ""), getattr(user, "looking_for", ""),
        getattr(user, "country", ""), getattr(user, "bio", ""),
        getattr(user, "goals", []), getattr(user, "interests", []),
        getattr(user, "skills", []), getattr(user, "languages", []),
    )
    return sum(bool(value) for value in values) / len(values)


def _candidate_score(current_user, candidate):
    current = {
        "goals": _terms(getattr(current_user, "goals", [])),
        "interests": _terms(getattr(current_user, "interests", [])),
        "skills": _terms(getattr(current_user, "skills", [])),
        "languages": _terms(getattr(current_user, "languages", [])),
        "country": _text(getattr(current_user, "country", "")),
        "profession": _text(getattr(current_user, "profession", "")),
        "looking_for": _text(getattr(current_user, "looking_for", "")),
    }
    other = {
        "goals": _terms(getattr(candidate, "goals", [])),
        "interests": _terms(getattr(candidate, "interests", [])),
        "skills": _terms(getattr(candidate, "skills", [])),
        "languages": _terms(getattr(candidate, "languages", [])),
        "country": _text(getattr(candidate, "country", "")),
        "profession": _text(getattr(candidate, "profession", "")),
        "looking_for": _text(getattr(candidate, "looking_for", "")),
    }

    components = {
        "shared_goals": _affinity(current["goals"], other["goals"]) * 28,
        "shared_interests": _affinity(current["interests"], other["interests"]) * 18,
        "shared_skills": _affinity(current["skills"], other["skills"]) * 12,
        "shared_languages": _affinity(current["languages"], other["languages"]) * 10,
        "same_country": 8 if current["country"] and current["country"] == other["country"] else 0,
        "intent_fit": 7 * sum((
            _intent_match(current["looking_for"], other["profession"]),
            _intent_match(current["profession"], other["looking_for"]),
        )),
        "candidate_trust": min(max(float(getattr(candidate, "trust_score", 0) or 0), 0), 100) * 0.03,
        "profile_quality": _profile_completeness(candidate) * 2,
    }
    matched_profile_signals = sum(bool(current[key] & other[key]) for key in ("goals", "interests", "skills", "languages"))
    matched_profile_signals += bool(components["same_country"])
    matched_profile_signals += bool(components["intent_fit"])
    confidence = "high" if matched_profile_signals >= 5 else "medium" if matched_profile_signals >= 3 else "low"
    details = {
        f"shared_{key}": sorted(current[key] & other[key])
        for key in ("goals", "interests", "skills", "languages")
        if current[key] & other[key]
    }
    return round(min(sum(components.values()), 100)), components, confidence, details


def find_best_matches(current_user, users):
    """Rank candidates without an LLM so results are fast and reproducible."""
    current_email = _text(getattr(current_user, "email", ""))
    matches = []
    for candidate in users or []:
        if _text(getattr(candidate, "email", "")) == current_email:
            continue
        score, components, confidence, details = _candidate_score(current_user, candidate)
        compatibility_keys = (
            "shared_goals", "shared_interests", "shared_skills", "shared_languages",
            "same_country", "intent_fit",
        )
        if score <= 0 or not any(components[key] > 0 for key in compatibility_keys):
            continue
        matches.append({
            "user": candidate,
            "score": score,
            "confidence": confidence,
            "signals": {key: round(value, 2) for key, value in components.items() if value > 0},
            "signal_details": details,
        })
    matches.sort(key=lambda item: (
        -item["score"],
        -float(getattr(item["user"], "trust_score", 0) or 0),
        str(getattr(item["user"], "id", "")),
    ))
    return matches
