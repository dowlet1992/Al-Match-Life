import os

from flask import Blueprint, render_template_string, request


def create_discovery_routes(deps):
    discovery_routes = Blueprint("discovery_routes", __name__)

    @discovery_routes.route("/matches/<email>")
    @deps["login_required"]
    def matches(email):
        current_user = deps["find_user_by_email"](email)

        if current_user is None:
            return "User not found"

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        matches_list = deps["find_best_matches"](current_user, deps["get_users"]())
        matches_html = ""
        current_settings = deps["normalize_user_ai_settings"](current_user.email)
        show_match_explanations = current_settings.get("ai_match_explanations", True) is True

        for match in matches_list:
            matched_user = match["user"]

            if not deps["can_show_user_in_ai_recommendations"](current_user.email, matched_user):
                continue

            score = match["score"]
            reasons = deps["explain_match"](current_user, matched_user) if show_match_explanations else []
            level = deps["get_match_level"](score)
            avatar_url = deps["get_avatar_url"](matched_user.email)

            reasons_html = ""
            for reason in reasons:
                reasons_html += f"<li>{deps['safe_text'](reason)}</li>"

            reasons_block_html = ""
            if show_match_explanations:
                reasons_block_html = f"""
                <div class="reasons">
                    <h3>{deps["safe_text"](ui.get("why_ai_recommends_person", "Why AI recommends this person:"))}</h3>
                    <ul>{reasons_html}</ul>
                </div>
                """

            matches_html += f"""
            <div class="match-card">
                <div class="match-top">
                    <img class="avatar" src="{avatar_url}" alt="Avatar">

                    <div class="match-info">
                        <h2>{deps["safe_text"](matched_user.name)}</h2>
                        <p>{deps["safe_text"](matched_user.profession)}</p>
                        <p class="country">{deps["safe_text"](matched_user.country)}</p>
                    </div>

                    <div class="score-box">
                        <div class="score">{score}%</div>
                        <div class="level">{deps["safe_text"](level)}</div>
                    </div>
                </div>

                <div class="details">
                    <p><b>{deps["safe_text"](ui.get("looking_for_label", "Looking for"))}:</b> {deps["safe_text"](matched_user.looking_for)}</p>
                    <p><b>{deps["safe_text"](ui.get("goals_label", "Goals"))}:</b> {deps["safe_text"](", ".join(matched_user.goals))}</p>
                    <p><b>{deps["safe_text"](ui.get("interests_label", "Interests"))}:</b> {deps["safe_text"](", ".join(matched_user.interests))}</p>
                    <p><b>{deps["safe_text"](ui.get("skills_label", "Skills"))}:</b> {deps["safe_text"](", ".join(matched_user.skills))}</p>
                </div>

                {reasons_block_html}

                <div class="actions">
                    <a href="/profile/{deps["safe_text"](matched_user.email)}?viewer={deps["safe_text"](current_user.email)}">{deps["safe_text"](ui.get("open_profile", "Open profile"))}</a>
                    <a href="/chat/{deps["safe_text"](current_user.email)}/{deps["safe_text"](matched_user.email)}" class="message">{deps["safe_text"](ui.get("write_message", "Write"))}</a>
                </div>
            </div>
            """

        if matches_html == "":
            matches_html = f"""
            <div class="empty-card">
                {deps["safe_text"](ui.get("ai_matches_empty", "No suitable AI Matches yet. Complete your profile, goals, interests, and skills."))}
            </div>
            """

        html = deps["open_html"]("matches.html")
        return render_template_string(
            html,
            name=deps["safe_text"](current_user.name),
            email=deps["safe_text"](current_user.email),
            matches=matches_html,
            ui=ui,
        )

    @discovery_routes.route("/search/<email>", methods=["GET", "POST"])
    @deps["login_required"]
    def search_page(email):
        current_user = deps["find_user_by_email"](email)
        if current_user is None:
            return "User not found"

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        results_html = ""

        if request.method == "POST":
            deps["validate_csrf_token"]()
            keyword = deps["clean_text"](request.form["keyword"]).strip().lower()

            for user in deps["get_users"]():
                if user.email.strip().lower() == current_user.email.strip().lower():
                    continue

                if deps["is_blocked"](current_user.email, user.email) or deps["is_blocked"](user.email, current_user.email):
                    continue

                if deps["is_restricted"](current_user.email, user.email) or deps["is_restricted"](user.email, current_user.email):
                    continue

                if deps["is_account_deactivated"](user):
                    continue

                privacy = deps["get_user_privacy"](user.email)

                if privacy.get("show_in_search") == False:
                    continue

                if privacy.get("vip_mode") == True:
                    continue

                searchable_text = (
                    str(user.name) + " " +
                    str(user.country) + " " +
                    str(user.bio) + " " +
                    str(user.profession) + " " +
                    str(user.looking_for) + " " +
                    " ".join(user.languages) + " " +
                    " ".join(user.goals) + " " +
                    " ".join(user.interests) + " " +
                    " ".join(user.skills)
                ).lower()

                if keyword in searchable_text:
                    results_html += deps["user_card"](user)

            if results_html == "":
                results_html = f"<div class='card'><p>{deps['safe_text'](ui.get('nothing_found', 'Nothing found.'))}</p></div>"

        html = deps["open_html"]("search.html")
        return render_template_string(
            html,
            email=deps["safe_text"](current_user.email),
            results=results_html,
            csrf_token_input=deps["csrf_input"](),
            ui=ui,
        )

    @discovery_routes.route("/radar/<email>")
    def radar_page(email):
        current_user = deps["find_user_by_email"](email)

        if current_user is None:
            return "User not found"

        current_settings = deps["normalize_user_ai_settings"](current_user.email)
        radar_enabled = current_settings.get("ai_life_radar", True) is True
        recommendations_enabled = current_settings.get("ai_recommendations", True) is True

        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

        if openai_key.startswith("sk-"):
            ai_status_text = f"🟢 Real AI активен · {openai_model}"
            ai_status_color = "#22c55e"
        else:
            ai_status_text = "🟡 AI fallback mode · добавьте OPENAI_API_KEY"
            ai_status_color = "#f59e0b"

        raw_matches = deps["find_best_matches"](current_user, deps["get_users"]()) if radar_enabled and recommendations_enabled else []
        seen_emails = set()
        cleaned_matches = []

        for match in raw_matches:
            matched_user = match.get("user") if isinstance(match, dict) else None

            if matched_user is None:
                continue

            matched_email = deps["normalize_email"](getattr(matched_user, "email", ""))

            if not matched_email or matched_email in seen_emails:
                continue

            if not deps["can_show_user_in_ai_recommendations"](current_user.email, matched_user):
                continue

            seen_emails.add(matched_email)
            cleaned_matches.append(match)

        life_actions = [
            {
                "title": "Усилить профиль",
                "text": "Добавьте цели, навыки, интересы и конкретный запрос. AI будет точнее подбирать людей.",
                "url": f"/edit_profile/{current_user.email}",
                "button": "Редактировать",
            },
            {
                "title": "Найти людей по профессии",
                "text": "Откройте AI Matches и посмотрите людей по профессии, интересам и общим целям.",
                "url": f"/matches/{current_user.email}",
                "button": "Найти людей",
            },
            {
                "title": "Добавить Proof Profile",
                "text": "Подтвердите опыт, навыки или достижения, чтобы повысить доверие к профилю.",
                "url": f"/proof/{current_user.email}/{current_user.email}",
                "button": "Повысить Trust",
            },
        ]
        action_cards_html = ""

        for index, action in enumerate(life_actions, start=1):
            action_cards_html += f"""
            <a class="action-card" href="{action['url']}">
                <div class="action-number">{index}</div>
                <div class="action-content">
                    <strong>{deps["safe_text"](action['title'])}</strong>
                    <span>{deps["safe_text"](action['text'])}</span>
                </div>
                <div class="action-open">{deps["safe_text"](action['button'])}</div>
            </a>
            """

        people_html = ""

        for match in cleaned_matches[:8]:
            matched_user = match["user"]
            score = int(match.get("score", 0))
            avatar_url = deps["get_avatar_url"](matched_user.email)

            ai_reasons = deps["explain_user_match"](current_user, matched_user)
            fallback_reasons = deps["explain_match"](current_user, matched_user)
            reasons = ai_reasons if ai_reasons else fallback_reasons

            reasons_html = ""
            for reason in reasons[:4]:
                reasons_html += f"<li>{deps['safe_text'](reason)}</li>"

            if reasons_html == "":
                reasons_html = "<li>AI пока не нашёл сильных объяснений. Заполните цели, интересы и навыки точнее.</li>"

            profession = deps["safe_text"](getattr(matched_user, "profession", ""))
            location = deps["safe_text"](getattr(matched_user, "location", ""))
            country = deps["safe_text"](getattr(matched_user, "country", ""))
            city = deps["safe_text"](getattr(matched_user, "city", ""))
            trust_score = deps["safe_text"](getattr(matched_user, "trust_score", 0))

            location_parts = []
            if city != "не указано":
                location_parts.append(city)
            if country != "не указано":
                location_parts.append(country)
            if not location_parts and location != "не указано":
                location_parts.append(location)

            location_text = ", ".join(location_parts) if location_parts else "Локация не указана"

            if score >= 80:
                match_label = "Очень сильное совпадение"
                score_class = "score-high"
            elif score >= 55:
                match_label = "Хороший потенциал"
                score_class = "score-mid"
            else:
                match_label = "Можно изучить"
                score_class = "score-low"

            people_html += f"""
            <article class="person-card">
                <div class="person-top">
                    <div class="avatar-ring">
                        <img src="{avatar_url}" alt="Avatar">
                    </div>

                    <div class="person-main">
                        <div class="person-name-row">
                            <h2>{deps["safe_text"](matched_user.name)}</h2>
                            <span class="trust-pill">Trust {trust_score}</span>
                        </div>
                        <p class="person-profession">{profession}</p>
                        <p class="person-location">📍 {deps["safe_text"](location_text)}</p>
                    </div>

                    <div class="score-box {score_class}">
                        <div class="score-value">{score}%</div>
                        <div class="score-label">{match_label}</div>
                    </div>
                </div>

                <div class="ai-explain-box">
                    <div class="ai-explain-head">
                        <span>🧠 AI объяснение</span>
                        <small>{deps["safe_text"](ai_status_text)}</small>
                    </div>
                    <ul>{reasons_html}</ul>
                </div>

                <div class="person-actions">
                    <a href="/profile/{matched_user.email}?viewer={current_user.email}" class="primary-action">Открыть профиль</a>
                    <a href="/chat/{current_user.email}/{matched_user.email}" class="secondary-action">Написать</a>
                </div>
            </article>
            """

        if people_html == "":
            if not radar_enabled:
                people_html = """
                <div class="empty-card">
                    <h2>AI Life Radar выключен</h2>
                    <p>Вы отключили AI Life Radar в настройках. Включите его в Settings → AI, чтобы снова получать персональные рекомендации.</p>
                </div>
                """
            elif not recommendations_enabled:
                people_html = """
                <div class="empty-card">
                    <h2>AI рекомендации выключены</h2>
                    <p>Вы отключили AI рекомендации в настройках. Система не будет подбирать людей, пока вы снова не включите эту функцию.</p>
                </div>
                """
            else:
                people_html = """
                <div class="empty-card">
                    <h2>AI Radar пока не нашёл подходящих людей</h2>
                    <p>Заполните профиль: цели, интересы, навыки, профессию и кого вы ищете. Также часть пользователей может быть скрыта из-за их Privacy & AI настроек.</p>
                </div>
                """

        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>AI Life Radar</title>
            <style>
                body{{margin:0;background:#0f172a;color:white;font-family:Arial,sans-serif;}}
                .page{{max-width:1120px;margin:auto;padding:30px;}}
                .back{{display:inline-flex;align-items:center;gap:8px;color:white;text-decoration:none;background:#1e293b;border:1px solid rgba(148,163,184,0.18);padding:12px 16px;border-radius:16px;margin-bottom:18px;font-weight:800;}}
                .hero{{background:radial-gradient(circle at top left,rgba(37,99,235,0.52),transparent 34%),linear-gradient(135deg,#1e293b,#172554 65%,#111827);padding:34px;border-radius:34px;margin-bottom:24px;border:1px solid rgba(148,163,184,0.14);box-shadow:0 22px 60px rgba(0,0,0,0.28);}}
                .hero-top{{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;}}
                .hero h1{{margin:0 0 10px 0;font-size:42px;letter-spacing:-1px;}}
                .hero p{{color:#cbd5e1;margin:0;font-size:17px;line-height:1.55;max-width:760px;}}
                .ai-status{{background:rgba(15,23,42,0.74);border:1px solid rgba(148,163,184,0.22);color:white;border-radius:999px;padding:10px 14px;font-size:13px;font-weight:900;display:inline-flex;align-items:center;gap:8px;box-shadow:0 12px 28px rgba(0,0,0,0.25);}}
                .status-dot{{width:10px;height:10px;border-radius:50%;background:{ai_status_color};box-shadow:0 0 0 6px rgba(34,197,94,0.10);}}
                .section{{background:#1e293b;padding:24px;border-radius:28px;margin-bottom:22px;border:1px solid rgba(148,163,184,0.12);box-shadow:0 16px 40px rgba(0,0,0,0.20);}}
                .section h2{{margin:0 0 8px 0;font-size:26px;}}
                .section p{{margin:0;color:#cbd5e1;line-height:1.5;}}
                .actions-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:18px;}}
                .action-card{{background:#0f172a;border:1px solid rgba(96,165,250,0.16);border-radius:18px;padding:14px;color:#dbeafe;font-weight:750;line-height:1.45;display:flex;gap:12px;align-items:flex-start;text-decoration:none;min-height:84px;transition:0.16s ease;}}
                .action-card:hover{{transform:translateY(-2px);background:#111c33;border-color:rgba(96,165,250,0.34);box-shadow:0 14px 30px rgba(0,0,0,0.22);}}
                .action-content{{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px;}}
                .action-content strong{{color:#f8fafc;font-size:15px;}}
                .action-content span{{color:#cbd5e1;font-size:13px;line-height:1.35;}}
                .action-open{{align-self:center;background:#2563eb;color:white;border-radius:999px;padding:8px 11px;font-size:12px;font-weight:900;white-space:nowrap;}}
                .action-number{{min-width:28px;height:28px;border-radius:50%;background:#2563eb;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:900;}}
                .person-card{{background:#1e293b;border:1px solid rgba(148,163,184,0.12);padding:22px;border-radius:28px;margin-bottom:18px;box-shadow:0 18px 44px rgba(0,0,0,0.22);}}
                .person-top{{display:flex;align-items:center;gap:18px;}}
                .avatar-ring{{width:84px;height:84px;border-radius:50%;padding:3px;background:linear-gradient(135deg,#2563eb,#8b5cf6,#ec4899);flex-shrink:0;}}
                .avatar-ring img{{width:100%;height:100%;border-radius:50%;object-fit:cover;background:#334155;border:3px solid #1e293b;box-sizing:border-box;}}
                .person-main{{flex:1;min-width:0;}}
                .person-name-row{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}}
                .person-name-row h2{{margin:0;font-size:25px;}}
                .trust-pill{{background:rgba(34,197,94,0.12);color:#4ade80;border:1px solid rgba(34,197,94,0.22);padding:5px 9px;border-radius:999px;font-size:12px;font-weight:900;}}
                .person-profession,.person-location{{margin:6px 0 0 0;color:#cbd5e1;}}
                .score-box{{min-width:150px;text-align:center;padding:14px 16px;border-radius:22px;background:#0f172a;border:1px solid rgba(148,163,184,0.12);}}
                .score-value{{font-size:30px;font-weight:900;}}
                .score-label{{font-size:12px;color:#cbd5e1;font-weight:800;margin-top:4px;}}
                .score-high .score-value{{color:#22c55e;}}
                .score-mid .score-value{{color:#f59e0b;}}
                .score-low .score-value{{color:#60a5fa;}}
                .ai-explain-box{{background:#0f172a;border:1px solid rgba(96,165,250,0.12);padding:16px;border-radius:20px;margin-top:18px;}}
                .ai-explain-head{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px;font-weight:900;}}
                .ai-explain-head small{{color:#94a3b8;font-weight:800;}}
                .ai-explain-box ul{{margin:0;padding-left:21px;color:#cbd5e1;line-height:1.65;}}
                .person-actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;}}
                .primary-action,.secondary-action{{text-decoration:none;color:white;border-radius:15px;padding:12px 16px;font-weight:900;display:inline-flex;align-items:center;justify-content:center;}}
                .primary-action{{background:#2563eb;}}
                .secondary-action{{background:#334155;}}
                .empty-card{{background:#1e293b;border:1px solid rgba(148,163,184,0.12);padding:28px;border-radius:26px;text-align:center;color:#cbd5e1;}}
                @media(max-width:760px){{.page{{padding:18px;}}.hero{{padding:24px;border-radius:26px;}}.hero h1{{font-size:32px;}}.person-top{{align-items:flex-start;}}.score-box{{min-width:112px;padding:12px;}}.score-value{{font-size:24px;}}}}
                @media(max-width:560px){{.person-top{{flex-direction:column;}}.score-box{{width:100%;box-sizing:border-box;}}.primary-action,.secondary-action{{width:100%;box-sizing:border-box;}}.action-card{{flex-direction:column;}}.action-open{{align-self:flex-start;}}}}
            </style>
        </head>

        <body>
            <div class="page">
                <a class="back" href="/dashboard/{current_user.email}">← Назад</a>

                <section class="hero">
                    <div class="hero-top">
                        <div>
                            <h1>🧠 AI Life Radar</h1>
                            <p>Персональные рекомендации людей, возможностей и действий на основе целей, интересов, навыков, доверия и контекста профиля.</p>
                        </div>
                        <div class="ai-status"><span class="status-dot"></span>{deps["safe_text"](ai_status_text)}</div>
                    </div>
                </section>

                <section class="section">
                    <h2>🎯 Что AI советует сделать сейчас</h2>
                    <p>Это быстрые действия, которые усилят профиль и помогут системе находить более точных людей.</p>
                    <div class="actions-grid">{action_cards_html}</div>
                </section>

                <section class="section">
                    <h2>Люди, которых стоит посмотреть сегодня</h2>
                    <p>AI выбрал людей, которые могут быть полезны для бизнеса, развития, дружбы, команды или будущих проектов. Сам пользователь, дубли, заблокированные профили и скрытые по Privacy & AI настройки не показываются.</p>
                </section>

                {people_html}
            </div>
        </body>
        </html>
        """

    return discovery_routes
