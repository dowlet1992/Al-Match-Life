from flask import Blueprint, abort, render_template, request


def joined(values):
    return ", ".join(values or []) if isinstance(values, (list, tuple)) else ""


def create_discovery_routes(deps):
    discovery_routes = Blueprint("discovery_routes", __name__)

    def current_account(identifier):
        user = deps["find_user_by_identifier"](identifier)
        if user is None:
            return None
        if deps["normalize_email"](deps["current_session_email"]()) != deps["normalize_email"](user.email):
            deps["log_security_event"]("discovery_owner_mismatch", deps["current_session_email"](), f"target={user.email}")
            abort(403)
        return user

    @discovery_routes.route("/matches/<email>")
    @deps["login_required"]
    def matches(email):
        current_user = current_account(email)
        if current_user is None:
            return "User not found", 404

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        copy = radar_copy(ui.get("language_code", "en"))
        settings = deps["normalize_user_ai_settings"](current_user.email)
        show_explanations = settings.get("ai_match_explanations", True) is True
        visible_matches = []
        for match in deps["find_best_matches"](current_user, deps["get_users"]()):
            matched_user = match.get("user") if isinstance(match, dict) else None
            if matched_user is None or not deps["can_show_user_in_ai_recommendations"](current_user.email, matched_user):
                continue
            try:
                score = max(0, min(100, int(match.get("score", 0))))
            except (TypeError, ValueError):
                score = 0
            reasons = []
            if show_explanations:
                signals = match.get("signals", {}) if isinstance(match.get("signals", {}), dict) else {}
                signal_details = match.get("signal_details", {}) if isinstance(match.get("signal_details", {}), dict) else {}
                for key in signals:
                    reason = copy.get(f"signal_{key}", "")
                    details = signal_details.get(key, [])
                    if reason and isinstance(details, list) and details:
                        reason = f"{reason}: {', '.join(str(value) for value in details[:3])}"
                    if reason:
                        reasons.append(reason)
                if not reasons:
                    reasons = deps["explain_match"](current_user, matched_user)
            if score >= 80:
                level = copy["strong"]
            elif score >= 55:
                level = copy["potential"]
            else:
                level = copy["explore"]
            visible_matches.append({
                "id": matched_user.id,
                "email": matched_user.email,
                "name": matched_user.name,
                "profession": matched_user.profession,
                "country": matched_user.country,
                "looking_for": matched_user.looking_for,
                "goals": joined(getattr(matched_user, "goals", [])),
                "interests": joined(getattr(matched_user, "interests", [])),
                "skills": joined(getattr(matched_user, "skills", [])),
                "score": score,
                "level": level,
                "avatar_url": deps["get_avatar_url"](matched_user.email),
                "reasons": reasons if isinstance(reasons, list) else [],
            })

        return render_template(
            "matches.html",
            email=current_user.email,
            user_id=current_user.id,
            shell_account_target=current_user.id,
            matches=visible_matches,
            show_match_explanations=show_explanations,
            ui=ui,
        )

    @discovery_routes.route("/search/<email>", methods=["GET", "POST"])
    @deps["login_required"]
    def search_page(email):
        current_user = current_account(email)
        if current_user is None:
            return "User not found", 404

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        results = []
        keyword = ""
        if request.method == "POST":
            deps["validate_csrf_token"]()
            keyword = deps["clean_text"](request.form.get("keyword", ""))[:120].strip().lower()
            for user in deps["get_users"]() if keyword else []:
                if deps["normalize_email"](user.email) == deps["normalize_email"](current_user.email):
                    continue
                if deps["is_blocked"](current_user.email, user.email) or deps["is_blocked"](user.email, current_user.email):
                    continue
                if deps["is_restricted"](current_user.email, user.email) or deps["is_restricted"](user.email, current_user.email):
                    continue
                if deps["is_account_deactivated"](user):
                    continue
                privacy = deps["get_user_privacy"](user.email)
                if privacy.get("show_in_search") is False or privacy.get("vip_mode") is True:
                    continue
                searchable_text = " ".join([
                    str(user.name), str(user.country), str(user.bio), str(user.profession),
                    str(user.looking_for), joined(getattr(user, "languages", [])),
                    joined(getattr(user, "goals", [])), joined(getattr(user, "interests", [])),
                    joined(getattr(user, "skills", [])),
                ]).lower()
                if keyword in searchable_text:
                    results.append({
                        "id": user.id,
                        "email": user.email,
                        "name": user.name,
                        "profession": user.profession,
                        "country": user.country,
                        "bio": user.bio,
                        "avatar_url": deps["get_avatar_url"](user.email),
                    })

        return render_template(
            "search.html",
            email=current_user.email,
            user_id=current_user.id,
            shell_account_target=current_user.id,
            results=results,
            searched=request.method == "POST",
            keyword=keyword,
            csrf_token_input=deps["csrf_input"](),
            ui=ui,
        )

    @discovery_routes.route("/radar/<email>")
    @deps["login_required"]
    def radar_page(email):
        current_user = current_account(email)
        if current_user is None:
            return "User not found", 404

        ui = deps["translation_bundle"](deps["get_current_language"](current_user))
        language = ui.get("language_code", "en")
        copy = radar_copy(language)
        settings = deps["normalize_user_ai_settings"](current_user.email)
        radar_enabled = settings.get("ai_life_radar", True) is True
        recommendations_enabled = settings.get("ai_recommendations", True) is True
        raw_matches = (
            deps["find_best_matches"](current_user, deps["get_users"]())
            if radar_enabled and recommendations_enabled else []
        )

        people = []
        seen_emails = set()
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
            try:
                score = max(0, min(100, int(match.get("score", 0))))
            except (TypeError, ValueError):
                score = 0
            # Radar is a deterministic recommendation system. Calling a
            # generative model once per candidate made this page slow and
            # produced explanations that could drift away from profile data.
            signals = match.get("signals", {}) if isinstance(match.get("signals", {}), dict) else {}
            signal_details = match.get("signal_details", {}) if isinstance(match.get("signal_details", {}), dict) else {}
            reasons = []
            for key in signals:
                reason = copy.get(f"signal_{key}", "")
                details = signal_details.get(key, [])
                if reason and isinstance(details, list) and details:
                    reason = f"{reason}: {', '.join(str(value) for value in details[:3])}"
                if reason:
                    reasons.append(reason)
            if not reasons:
                reasons = deps["explain_match"](current_user, matched_user)
            reasons = reasons[:4] if isinstance(reasons, list) else []
            if not reasons:
                reasons = [copy["no_reason"]]

            location_parts = []
            for value in (getattr(matched_user, "city", ""), getattr(matched_user, "country", ""), getattr(matched_user, "location", "")):
                value = str(value or "").strip()
                if value and value.lower() not in {"не указано", "not specified", "nicht angegeben"} and value not in location_parts:
                    location_parts.append(value)
            if score >= 80:
                score_class, match_label = "score-high", copy["strong"]
            elif score >= 55:
                score_class, match_label = "score-mid", copy["potential"]
            else:
                score_class, match_label = "score-low", copy["explore"]
            people.append({
                "id": matched_user.id,
                "email": matched_user.email,
                "name": matched_user.name,
                "profession": getattr(matched_user, "profession", ""),
                "location": ", ".join(location_parts) or copy["no_location"],
                "trust_score": getattr(matched_user, "trust_score", 0),
                "avatar_url": deps["get_avatar_url"](matched_user.email),
                "score": score,
                "score_class": score_class,
                "match_label": match_label,
                "confidence_text": copy.get(f"confidence_{match.get('confidence', 'low')}", copy["confidence_low"]),
                "reasons": reasons,
            })
            if len(people) == 8:
                break

        if not radar_enabled:
            empty = {"title": copy["radar_off"], "text": copy["radar_off_help"]}
        elif not recommendations_enabled:
            empty = {"title": copy["recommendations_off"], "text": copy["recommendations_off_help"]}
        else:
            empty = {"title": copy["empty"], "text": copy["empty_help"]}

        actions = [
            {"title": copy["improve"], "text": copy["improve_help"], "url": f"/edit_profile/{current_user.email}", "button": copy["edit"]},
            {"title": copy["find"], "text": copy["find_help"], "url": f"/matches/{current_user.id}", "button": copy["find_button"]},
            {"title": copy["proof"], "text": copy["proof_help"], "url": f"/proof/{current_user.email}/{current_user.email}", "button": copy["trust"]},
        ]
        return render_template(
            "radar.html",
            ui=ui,
            copy=copy,
            email=current_user.email,
            user_id=current_user.id,
            shell_account_target=current_user.id,
            actions=actions,
            people=people,
            empty=empty,
            status_text=ui.get("recommendations_ready", copy["status"]),
        )

    return discovery_routes


def radar_copy(language):
    copies = {
        "ru": {
            "title": "NOVIX Radar", "intro": "Персональные рекомендации людей и действий на основе целей, интересов, навыков и доверия.",
            "status": "Рекомендации", "actions_title": "Что AI советует сделать сейчас", "actions_intro": "Быстрые действия для более точных рекомендаций.",
            "people_title": "Люди, которых стоит посмотреть сегодня", "people_intro": "Рекомендательная система учитывает профиль и настройки приватности.",
            "explanation": "Объяснение рекомендации", "open": "Открыть профиль", "write": "Написать",
            "improve": "Усилить профиль", "improve_help": "Добавьте цели, навыки, интересы и конкретный запрос.", "edit": "Редактировать",
            "find": "Найти людей по профессии", "find_help": "Посмотрите совпадения по профессии, интересам и целям.", "find_button": "Найти людей",
            "proof": "Добавить Proof Profile", "proof_help": "Подтвердите опыт, навыки или достижения.", "trust": "Повысить Trust",
            "strong": "Очень сильное совпадение", "potential": "Хороший потенциал", "explore": "Можно изучить",
            "no_reason": "Заполните цели, интересы и навыки точнее.", "no_location": "Локация не указана",
            "radar_off": "NOVIX Radar выключен", "radar_off_help": "Включите NOVIX Radar в настройках, чтобы получать рекомендации.",
            "recommendations_off": "AI рекомендации выключены", "recommendations_off_help": "Включите рекомендации в настройках.",
            "empty": "AI Radar пока не нашёл подходящих людей", "empty_help": "Дополните профиль или проверьте настройки Privacy & AI.",
            "trust_label": "Доверие", "confidence_high": "Высокая точность", "confidence_medium": "Средняя точность", "confidence_low": "Предварительная рекомендация",
            "signal_shared_goals": "Совпадают цели", "signal_shared_interests": "Есть общие интересы", "signal_shared_skills": "Совпадают навыки",
            "signal_shared_languages": "Есть общий язык общения", "signal_same_country": "Вы находитесь в одной стране",
            "signal_intent_fit": "Запрос одного профиля соответствует опыту другого", "signal_candidate_trust": "Профиль имеет подтверждённый уровень доверия", "signal_profile_quality": "Профиль достаточно заполнен",
        },
        "de": {
            "title": "NOVIX Radar", "intro": "Personalisierte Empfehlungen auf Basis von Zielen, Interessen, Fähigkeiten und Vertrauen.",
            "status": "Empfehlungen", "actions_title": "Empfohlene nächste Schritte", "actions_intro": "Schnelle Schritte für präzisere Empfehlungen.",
            "people_title": "Heute interessante Personen", "people_intro": "Das Empfehlungssystem berücksichtigt Profil und Datenschutz.",
            "explanation": "Erklärung der Empfehlung", "open": "Profil öffnen", "write": "Schreiben",
            "improve": "Profil verbessern", "improve_help": "Ergänzen Sie Ziele, Fähigkeiten und Interessen.", "edit": "Bearbeiten",
            "find": "Personen nach Beruf finden", "find_help": "Entdecken Sie Übereinstimmungen bei Beruf, Interessen und Zielen.", "find_button": "Personen finden",
            "proof": "Proof Profile ergänzen", "proof_help": "Belegen Sie Erfahrung, Fähigkeiten oder Erfolge.", "trust": "Trust erhöhen",
            "strong": "Sehr starke Übereinstimmung", "potential": "Gutes Potenzial", "explore": "Interessant",
            "no_reason": "Ergänzen Sie Ziele, Interessen und Fähigkeiten.", "no_location": "Ort nicht angegeben",
            "radar_off": "NOVIX Radar ist deaktiviert", "radar_off_help": "Aktivieren Sie Radar in den Einstellungen.",
            "recommendations_off": "AI-Empfehlungen sind deaktiviert", "recommendations_off_help": "Aktivieren Sie Empfehlungen in den Einstellungen.",
            "empty": "Noch keine passenden Personen", "empty_help": "Ergänzen Sie Ihr Profil oder prüfen Sie Privacy & AI.",
            "trust_label": "Vertrauen", "confidence_high": "Hohe Genauigkeit", "confidence_medium": "Mittlere Genauigkeit", "confidence_low": "Vorläufige Empfehlung",
            "signal_shared_goals": "Gemeinsame Ziele", "signal_shared_interests": "Gemeinsame Interessen", "signal_shared_skills": "Ähnliche Fähigkeiten",
            "signal_shared_languages": "Gemeinsame Sprache", "signal_same_country": "Sie befinden sich im selben Land",
            "signal_intent_fit": "Die Suche eines Profils passt zur Erfahrung des anderen", "signal_candidate_trust": "Bestätigtes Vertrauensniveau", "signal_profile_quality": "Ausführlich ausgefülltes Profil",
        },
        "tr": {
            "title": "NOVIX Radar", "intro": "Hedeflerinize, ilgi alanlarınıza, becerilerinize ve güven düzeyinize göre kişiselleştirilmiş öneriler.",
            "status": "Öneriler", "actions_title": "AI'ın şimdi önerdiği adımlar", "actions_intro": "Daha isabetli öneriler için hızlı adımlar.",
            "people_title": "Bugün incelemeye değer kişiler", "people_intro": "Öneri sistemi profil ve gizlilik ayarlarını dikkate alır.",
            "explanation": "Önerinin gerekçesi", "open": "Profili aç", "write": "Mesaj yaz",
            "improve": "Profilinizi güçlendirin", "improve_help": "Hedeflerinizi, becerilerinizi, ilgi alanlarınızı ve aradığınız kişiyi netleştirin.", "edit": "Düzenle",
            "find": "Mesleğe göre kişileri bulun", "find_help": "Meslek, ilgi alanları ve hedeflere göre eşleşmeleri keşfedin.", "find_button": "Kişileri bul",
            "proof": "Proof Profile ekleyin", "proof_help": "Deneyiminizi, becerilerinizi veya başarılarınızı doğrulayın.", "trust": "Güveni artır",
            "strong": "Çok güçlü eşleşme", "potential": "İyi potansiyel", "explore": "İncelemeye değer",
            "no_reason": "Daha isabetli sonuçlar için hedeflerinizi, ilgi alanlarınızı ve becerilerinizi ayrıntılandırın.", "no_location": "Konum belirtilmemiş",
            "radar_off": "NOVIX Radar kapalı", "radar_off_help": "Öneri almak için ayarlardan NOVIX Radar'ı etkinleştirin.",
            "recommendations_off": "AI önerileri kapalı", "recommendations_off_help": "Ayarlardan AI önerilerini etkinleştirin.",
            "empty": "AI Radar henüz uygun bir kişi bulamadı", "empty_help": "Profilinizi tamamlayın veya Gizlilik ve AI ayarlarını kontrol edin.",
            "trust_label": "Güven", "confidence_high": "Yüksek doğruluk", "confidence_medium": "Orta doğruluk", "confidence_low": "Ön değerlendirme",
            "signal_shared_goals": "Ortak hedefler", "signal_shared_interests": "Ortak ilgi alanları", "signal_shared_skills": "Benzer beceriler",
            "signal_shared_languages": "Ortak iletişim dili", "signal_same_country": "Aynı ülkedesiniz",
            "signal_intent_fit": "Bir profilin aradığı destek diğerinin deneyimiyle eşleşiyor", "signal_candidate_trust": "Doğrulanmış güven göstergeleri", "signal_profile_quality": "Yeterince tamamlanmış profil",
        },
    }
    return copies.get(language, {
        "title": "NOVIX Radar", "intro": "Personalized recommendations based on goals, interests, skills and trust.",
        "status": "Recommendations", "actions_title": "Recommended next steps", "actions_intro": "Quick actions for more accurate recommendations.",
        "people_title": "People worth viewing today", "people_intro": "The recommendation system respects profile and privacy settings.",
        "explanation": "Recommendation explanation", "open": "Open profile", "write": "Write",
        "improve": "Improve your profile", "improve_help": "Add goals, skills, interests and a clear request.", "edit": "Edit",
        "find": "Find people by profession", "find_help": "Explore matches by profession, interests and goals.", "find_button": "Find people",
        "proof": "Add Proof Profile", "proof_help": "Verify experience, skills or achievements.", "trust": "Increase Trust",
        "strong": "Very strong match", "potential": "Good potential", "explore": "Worth exploring",
        "no_reason": "Add more precise goals, interests and skills.", "no_location": "Location not specified",
        "radar_off": "NOVIX Radar is disabled", "radar_off_help": "Enable Radar in settings to receive recommendations.",
        "recommendations_off": "AI recommendations are disabled", "recommendations_off_help": "Enable recommendations in settings.",
        "empty": "AI Radar found no suitable people yet", "empty_help": "Complete your profile or review Privacy & AI settings.",
        "trust_label": "Trust", "confidence_high": "High confidence", "confidence_medium": "Medium confidence", "confidence_low": "Early recommendation",
        "signal_shared_goals": "Shared goals", "signal_shared_interests": "Shared interests", "signal_shared_skills": "Matching skills",
        "signal_shared_languages": "A shared communication language", "signal_same_country": "You are in the same country",
        "signal_intent_fit": "One profile's request matches the other's experience", "signal_candidate_trust": "Verified trust signals", "signal_profile_quality": "A sufficiently complete profile",
    })
