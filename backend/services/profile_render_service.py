def render_profile_media(post, clean_text, safe_text):
    media_html = ""
    media_items = post.get("media_items", [])
    if not isinstance(media_items, list):
        media_items = []

    if not media_items and post.get("media_url"):
        media_items = [{"url": post.get("media_url", ""), "type": post.get("media_type", ""), "name": "media"}]

    for media in media_items[:4]:
        media_url = safe_text(media.get("url", ""))
        media_type = clean_text(media.get("type", ""))
        if not media_url:
            continue

        if media_type == "image":
            media_html += f'<img class="profile-post-media" src="{media_url}" alt="Media">'
        elif media_type == "video":
            media_html += f'<video class="profile-post-media" src="{media_url}" controls playsinline></video>'
        elif media_type == "audio":
            media_html += f'<audio src="{media_url}" controls style="width:100%;margin-top:12px;"></audio>'

    return media_html


def render_profile_hashtags(post, clean_text, safe_text):
    hashtags_html = ""
    hashtags = post.get("hashtags", [])
    if not isinstance(hashtags, list):
        return hashtags_html

    for tag in hashtags[:8]:
        clean_tag = clean_text(tag).replace("#", "")
        if clean_tag:
            hashtags_html += f'<span class="profile-tag">#{safe_text(clean_tag)}</span>'

    return hashtags_html


def list_count(post, field_name):
    values = post.get(field_name, [])
    return len(values) if isinstance(values, list) else 0


def render_profile_post_card(post, viewer_email, clean_text, safe_text):
    media_html = render_profile_media(post, clean_text, safe_text)
    hashtags_html = render_profile_hashtags(post, clean_text, safe_text)
    post_type = safe_text(post.get("type", "Публикация"))
    post_text = safe_text(post.get("text", ""))
    post_date = safe_text(post.get("date", post.get("created_at", "")))
    post_id = safe_text(post.get("id", ""))

    return f"""
        <article class="profile-post-card">
            <div class="profile-post-top">
                <div>
                    <div class="profile-post-type">{post_type}</div>
                    <div class="profile-post-date">{post_date}</div>
                </div>
                <a class="profile-post-open" href="/post/{safe_text(viewer_email)}/{post_id}">Открыть</a>
            </div>
            <p class="profile-post-text">{post_text}</p>
            {media_html}
            <div class="profile-tags">{hashtags_html}</div>
            <div class="profile-post-actions">
                <span>♡ {list_count(post, "likes")}</span>
                <span>💬 {list_count(post, "comments")}</span>
                <span>🔖 {list_count(post, "saves")}</span>
            </div>
        </article>
        """


def profile_empty_text(current_tab):
    if current_tab == "news":
        return "Пока нет новостей, мыслей или идей."
    if current_tab == "projects":
        return "Пока нет проектов или поиска партнёров."
    if current_tab == "media":
        return "Пока нет фото или видео."
    if current_tab == "proof":
        return "Пока нет Proof-публикаций."
    return "Пока нет активности в этом разделе."


def render_profile_empty_card(current_tab, safe_text):
    return f"""
        <div class="profile-empty-card">
            <h3>Пусто</h3>
            <p>{safe_text(profile_empty_text(current_tab))}</p>
        </div>
        """


def render_profile_posts(posts, current_tab, viewer_email, clean_text, safe_text):
    posts_html = ""

    for post in posts:
        posts_html += render_profile_post_card(post, viewer_email, clean_text, safe_text)

    if not posts_html:
        return render_profile_empty_card(current_tab, safe_text)

    return posts_html


def render_profile_tabs(current_tab, counts, owner_email, viewer_email, safe_text):
    tabs = [
        ("all", "Все", counts.get("all", 0)),
        ("news", "Новости", counts.get("news", 0)),
        ("projects", "Проекты", counts.get("projects", 0)),
        ("media", "Фото/Видео", counts.get("media", 0)),
        ("proof", "Proof", counts.get("proof", 0)),
    ]
    tabs_html = ""

    for tab_key, tab_title, tab_count in tabs:
        active_class = "active" if current_tab == tab_key else ""
        tabs_html += f"""
            <a class="profile-tab {active_class}" href="/profile/{safe_text(owner_email)}?viewer={safe_text(viewer_email)}&tab={safe_text(tab_key)}">
                <span>{safe_text(tab_title)}</span>
                <strong>{tab_count}</strong>
            </a>
            """

    return tabs_html


def render_profile_stats(owner_email, viewer_email, counts, following_count, followers_count, show_activity, safe_text):
    if not show_activity:
        return """
        <div class="profile-stats">
            <div class="profile-stat"><span>Активность</span><strong>—</strong></div>
            <div class="profile-stat"><span>Подписки</span><strong>—</strong></div>
            <div class="profile-stat"><span>Подписчики</span><strong>—</strong></div>
        </div>
        """

    return f"""
    <div class="profile-stats">
        <a class="profile-stat" href="/profile/{safe_text(owner_email)}?viewer={safe_text(viewer_email)}&tab=all"><span>Активность</span><strong>{counts.get("all", 0)}</strong></a>
        <a class="profile-stat" href="/following/{safe_text(owner_email)}"><span>Подписки</span><strong>{following_count}</strong></a>
        <a class="profile-stat" href="/followers/{safe_text(owner_email)}"><span>Подписчики</span><strong>{followers_count}</strong></a>
    </div>
    """


def profile_clean_value(value, clean_text):
    cleaned = clean_text(value).strip()
    if cleaned.lower() in {"", "nicht angegeben", "не указано", "none", "null", "nan"}:
        return ""
    return cleaned


def profile_list_text(values, clean_text):
    if values is None:
        return ""
    if isinstance(values, list):
        cleaned_items = [profile_clean_value(item, clean_text) for item in values if profile_clean_value(item, clean_text)]
        return ", ".join(cleaned_items)
    if isinstance(values, str):
        cleaned_items = [
            profile_clean_value(item.strip(), clean_text)
            for item in values.replace(";", ",").split(",")
            if profile_clean_value(item.strip(), clean_text)
        ]
        return ", ".join(cleaned_items)
    return profile_clean_value(values, clean_text)


def render_profile_info_row(label, value, clean_text, safe_text):
    value = profile_clean_value(value, clean_text)
    if not value:
        return ""
    return f'<div class="profile-info-row"><div class="profile-info-label">{safe_text(label)}</div><div class="profile-info-value">{safe_text(value)}</div></div>'


def render_profile_header_text(user, clean_text, safe_text):
    profession_text = profile_clean_value(getattr(user, "profession", ""), clean_text)
    country_text = profile_clean_value(getattr(user, "country", ""), clean_text)
    bio_text = profile_clean_value(getattr(user, "bio", ""), clean_text)

    profile_meta_parts = [item for item in [profession_text, country_text] if item]
    profile_meta_html = f'<p class="profile-sub">{safe_text(" · ".join(profile_meta_parts))}</p>' if profile_meta_parts else ""
    profile_bio_html = f'<p class="profile-sub">{safe_text(bio_text)}</p>' if bio_text else ""

    return profile_meta_html, profile_bio_html


def render_profile_info(user, clean_text, safe_text):
    rows = ""
    rows += render_profile_info_row("Возраст", getattr(user, "age", ""), clean_text, safe_text)
    rows += render_profile_info_row("Языки", profile_list_text(getattr(user, "languages", []), clean_text), clean_text, safe_text)
    rows += render_profile_info_row("Цели", profile_list_text(getattr(user, "goals", []), clean_text), clean_text, safe_text)
    rows += render_profile_info_row("Интересы", profile_list_text(getattr(user, "interests", []), clean_text), clean_text, safe_text)
    rows += render_profile_info_row("Навыки", profile_list_text(getattr(user, "skills", []), clean_text), clean_text, safe_text)

    if not rows:
        return '<div class="profile-empty-mini">Профиль пока без подробной информации.</div>'

    return rows
