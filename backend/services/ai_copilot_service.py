import re


MODES = {
    "profile": {
        "title": "AI Profile Coach",
        "instruction": "Analyze the user's profile and give practical steps to improve trust, clarity, attractiveness, and usefulness inside NOVIX. Focus on profile quality, positioning, goals, skills, and what to add or rewrite.",
    },
    "match": {
        "title": "AI Match Advisor",
        "instruction": "Help the user understand what kind of people they should meet: friends, mentors, business partners, clients, investors, local contacts, or communities. Give matching logic and concrete next steps.",
    },
    "business": {
        "title": "AI Business Helper",
        "instruction": "Help the user with business development, networking, finding partners, clients, sponsors, project positioning, and step-by-step execution. Be realistic and practical.",
    },
    "content": {
        "title": "AI Content Ideas",
        "instruction": "Create useful content ideas for AI Discover based on the user's goals, interests, profession, languages, and learned feed behavior. Give post ideas, hooks, hashtags, and why each idea can work.",
    },
    "life": {
        "title": "AI Life Assistant",
        "instruction": "Help the user with personal planning, learning, discipline, daily progress, priorities, and clear next actions. Be supportive but realistic.",
    },
    "general": {
        "title": "AI Core General",
        "instruction": "Answer the user's question as the main AI assistant inside NOVIX. Use context, be honest, practical, and structured.",
    },
}


def mode_config(mode, clean_text=str):
    normalized = clean_text(mode).strip().lower()
    return MODES.get(normalized, MODES["general"])


def numeric_claims(value):
    claims = set()
    for match in re.findall(r"(?<!\w)\d[\d\s.,]*\d|(?<!\w)\d(?!\w)", str(value or "")):
        normalized = re.sub(r"\D", "", match)
        if normalized:
            claims.add(normalized)
    return claims


def grounded_revision(answer, verified_context, call_chat):
    """Remove unsupported precision from an otherwise grounded local answer."""
    unsupported_numbers = numeric_claims(answer) - numeric_claims(verified_context)
    if not answer or not verified_context or not unsupported_numbers:
        return answer
    revision = call_chat([
        {
            "role": "system",
            "content": (
                "You are a strict grounding editor. Rewrite the draft in its original language. "
                "Keep only claims explicitly supported by VERIFIED KNOWLEDGE. Remove every number, "
                "date, statistic, office-holder and precise detail absent from that knowledge. "
                "Do not add new facts. Return only the corrected answer."
            ),
        },
        {
            "role": "user",
            "content": f"VERIFIED KNOWLEDGE:\n{verified_context}\n\nDRAFT:\n{answer}",
        },
    ], temperature=0.0, max_tokens=600, strict=True)
    if revision and not (numeric_claims(revision) - numeric_claims(verified_context)):
        return revision
    return answer


def generate_answer(user, user_question, mode, deps):
    user_question = deps["clean_text"](user_question)[:4000]
    config = mode_config(mode, deps["clean_text"])
    if not user_question:
        return "Напишите вопрос или задачу для AI."

    cached = deps["cached_answer"](user.email, mode, user_question)
    if cached:
        return cached

    user_context = deps["build_user_context"](user)
    verified_context, verified_sources = deps["retrieve_verified_context"](user_question)
    system_prompt = (
        "You are NOVIX Core Assistant. You are the intelligent layer of the app, not a generic chatbot. "
        "Use the user's profile, goals, interests, skills, languages, trust signals, and AI Discover learning. "
        "Accuracy is more important than sounding confident. Never invent facts, statistics, laws, memberships, dates, or sources. "
        "If you are not certain, explicitly say that the fact must be verified. Follow the language of the user's latest question. "
        "Never mix scripts or insert Chinese characters into a Russian answer. Before answering, silently check every factual claim for internal consistency. "
        "When VERIFIED KNOWLEDGE is supplied, treat it as authoritative and do not contradict it. If VERIFIED KNOWLEDGE is supplied, "
        "use only facts explicitly present there; do not add exact figures, dates, names, or statistics from memory. "
        "Never claim that an answer was externally verified when no verified knowledge was supplied. Be concise, practical, structured, and honest. "
        f"Current mode: {config.get('title')}. Mode instruction: {config.get('instruction')}"
    )
    user_prompt = (
        f"User profile and AI memory context:\n{user_context}\n\nUser question:\n{user_question}\n\n"
        f"VERIFIED KNOWLEDGE (may be empty):\n{verified_context or 'No matching verified local source.'}\n\n"
        "Give a professional answer with clear next steps. For comparisons, use a compact table or clearly parallel points."
    )
    answer = deps["call_chat"]([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ], temperature=0.1, max_tokens=700)
    if verified_context and answer:
        answer = grounded_revision(answer, verified_context, deps["call_chat"])
    if verified_sources and answer:
        source_label = "Источники знаний" if any("а" <= char.lower() <= "я" for char in user_question) else "Knowledge sources"
        answer = f"{answer}\n\n{source_label}: " + "; ".join(dict.fromkeys(verified_sources))
    return answer
