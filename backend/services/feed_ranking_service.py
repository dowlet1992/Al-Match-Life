def clean_list_items(values, clean_text):
    if values is None:
        return []

    if isinstance(values, list):
        raw_items = values
    elif isinstance(values, str):
        raw_items = values.replace(";", ",").split(",")
    else:
        raw_items = []

    clean_items = []
    for item in raw_items:
        item = clean_text(item).strip()
        if item and item.lower() not in {"nicht angegeben", "не указано", "none", "null"}:
            clean_items.append(item)

    return clean_items


def build_user_keywords(user, clean_text):
    user_keywords = []
    user_keywords.extend(clean_list_items(getattr(user, "interests", []), clean_text))
    user_keywords.extend(clean_list_items(getattr(user, "goals", []), clean_text))
    user_keywords.extend(clean_list_items(getattr(user, "skills", []), clean_text))
    user_keywords.append(getattr(user, "profession", ""))
    user_keywords.append(getattr(user, "looking_for", ""))
    user_keywords.append(getattr(user, "country", ""))

    normalized_keywords = []
    for keyword in user_keywords:
        keyword = clean_text(keyword).lower()
        if keyword and keyword != "не указано" and len(keyword) > 2:
            normalized_keywords.append(keyword)

    return normalized_keywords


def rank_feed_posts(current_user, posts, deps):
    current_settings = deps["normalize_user_ai_settings"](current_user.email)
    ai_feed_enabled = current_settings.get("ai_recommendations", True) is True
    ai_activity_enabled = current_settings.get("ai_activity_analysis", True) is True

    ranked_posts = []
    feed_changed = False

    user_language_codes = deps["get_user_language_signals"](current_user)
    if not user_language_codes:
        user_language_codes = [deps["get_current_language"](current_user)]

    user_language_names = []
    for language_code in user_language_codes:
        normalized_language = deps["normalize_content_language_code"](language_code)
        language_name = deps["content_languages"]().get(
            normalized_language,
            deps["supported_languages"]().get(language_code, language_code),
        )
        if language_name not in user_language_names:
            user_language_names.append(language_name)

    normalized_keywords = build_user_keywords(current_user, deps["clean_text"])

    for post in posts:
        author_email = deps["normalize_email"](post.get("email", ""))

        if not author_email:
            continue

        if not deps["can_view_feed_post"](current_user.email, post):
            continue

        author = deps["find_user_by_email"](author_email)
        if author is None:
            continue

        content_language = deps["normalize_content_language_code"](post.get("language", ""))
        if content_language == "unknown":
            content_language = deps["detect_content_language"](" ".join([
                str(post.get("type", "")),
                str(post.get("text", "")),
                str(post.get("location", "")),
                " ".join(post.get("hashtags", [])),
            ]))
            post["language"] = content_language
            feed_changed = True

        language_score, language_reason = deps["score_language_match"](current_user, content_language)

        post_text_for_ai = deps["clean_text"](" ".join([
            str(post.get("type", "")),
            str(post.get("text", "")),
            str(post.get("location", "")),
            " ".join(post.get("hashtags", [])),
        ])).lower()

        interest_score = 0
        interest_reasons = []
        for keyword in normalized_keywords:
            if keyword and keyword in post_text_for_ai:
                interest_score += 18
                if len(interest_reasons) < 3:
                    interest_reasons.append(f"Совпадает с вашим интересом: {keyword}")

        engagement_score = min(len(post.get("likes", [])) * 2, 20)
        engagement_score += min(len(post.get("comments", [])) * 3, 24)
        engagement_score += min(len(post.get("saves", [])) * 4, 28)

        learning_score, learning_reasons = deps["calculate_ai_learning_boost"](
            current_user.email,
            post,
            content_language,
        )

        try:
            recency_score = min(int(post.get("id", 0)), 100) / 10
        except Exception:
            recency_score = 0

        own_post_penalty = -8 if author_email == deps["normalize_email"](current_user.email) else 0
        final_score = language_score + interest_score + engagement_score + learning_score + recency_score + own_post_penalty

        ai_reasons = []
        if language_reason:
            ai_reasons.append(language_reason)
        ai_reasons.extend(interest_reasons)
        ai_reasons.extend(learning_reasons)
        if engagement_score >= 10:
            ai_reasons.append("Публикация получает активность от пользователей")
        if not ai_reasons:
            ai_reasons.append("AI показывает это как новый контент для изучения ваших интересов")
        if not ai_feed_enabled:
            ai_reasons = ["AI-рекомендации выключены: показана обычная лента"]
        elif not ai_activity_enabled:
            ai_reasons.append("Анализ вашей активности выключен, поэтому персонализация ограничена")

        ranked_posts.append({
            "post": post,
            "author": author,
            "score": final_score,
            "ai_reasons": ai_reasons[:4],
            "content_language": content_language,
        })

    if ai_feed_enabled:
        ranked_posts.sort(key=lambda item: item.get("score", 0), reverse=True)
    else:
        ranked_posts.reverse()

    return {
        "ranked_posts": ranked_posts,
        "feed_changed": feed_changed,
        "user_language_codes": user_language_codes,
        "user_language_names": user_language_names,
        "ai_feed_enabled": ai_feed_enabled,
        "ai_activity_enabled": ai_activity_enabled,
    }
