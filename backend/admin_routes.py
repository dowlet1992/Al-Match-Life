from flask import Blueprint, redirect, render_template, request


VALID_STATUSES = ("new", "reviewing", "resolved", "dismissed")


def create_admin_routes(deps):
    admin_routes = Blueprint("admin_routes", __name__)

    def page_copy(admin_user):
        ui = deps["translation_bundle"](deps["get_current_language"](admin_user))
        language = ui.get("language_code", "en")
        copy = {
            "ru": {
                "title": "Moderation", "subtitle": "Жалобы, статусы и действия модерации",
                "total": "Всего", "open": "Открытые", "new": "Новые", "reviewing": "В проверке",
                "resolved": "Решены", "dismissed": "Отклонены", "all": "Все", "report": "Жалоба",
                "reporter": "Автор жалобы", "target": "Цель", "created": "Создано", "reviewed": "Проверено",
                "no_details": "Комментарий не указан.", "last_action": "Последнее действие",
                "no_note": "Заметки модератора пока нет.", "action": "Действие",
                "note": "Заметка модератора", "save": "Сохранить", "empty": "Жалоб нет",
                "empty_help": "По выбранному фильтру ничего не найдено.",
            },
            "de": {
                "title": "Moderation", "subtitle": "Meldungen, Status und Moderationsaktionen",
                "total": "Gesamt", "open": "Offen", "new": "Neu", "reviewing": "In Prüfung",
                "resolved": "Gelöst", "dismissed": "Abgewiesen", "all": "Alle", "report": "Meldung",
                "reporter": "Gemeldet von", "target": "Ziel", "created": "Erstellt", "reviewed": "Geprüft",
                "no_details": "Kein Kommentar angegeben.", "last_action": "Letzte Aktion",
                "no_note": "Noch keine Moderationsnotiz.", "action": "Aktion",
                "note": "Moderationsnotiz", "save": "Speichern", "empty": "Keine Meldungen",
                "empty_help": "Für diesen Filter wurden keine Einträge gefunden.",
            },
            "en": {
                "title": "Moderation", "subtitle": "Reports, statuses and moderation actions",
                "total": "Total", "open": "Open", "new": "New", "reviewing": "Reviewing",
                "resolved": "Resolved", "dismissed": "Dismissed", "all": "All", "report": "Report",
                "reporter": "Reporter", "target": "Target", "created": "Created", "reviewed": "Reviewed",
                "no_details": "No comment provided.", "last_action": "Last action",
                "no_note": "No moderator note yet.", "action": "Action",
                "note": "Moderator note", "save": "Save", "empty": "No reports",
                "empty_help": "Nothing matched the selected filter.",
            },
            "tr": {
                "title": "Moderasyon", "subtitle": "Bildirimler, durumlar ve moderasyon işlemleri",
                "total": "Toplam", "open": "Açık", "new": "Yeni", "reviewing": "İnceleniyor",
                "resolved": "Çözüldü", "dismissed": "Reddedildi", "all": "Tümü", "report": "Bildirim",
                "reporter": "Bildiren", "target": "Hedef", "created": "Oluşturuldu", "reviewed": "İncelendi",
                "no_details": "Açıklama verilmedi.", "last_action": "Son işlem",
                "no_note": "Henüz moderatör notu yok.", "action": "İşlem",
                "note": "Moderatör notu", "save": "Kaydet", "empty": "Bildirim yok",
                "empty_help": "Seçilen filtreyle eşleşen kayıt yok.",
            },
        }
        return ui, copy.get(language, copy["en"])

    @admin_routes.route("/admin/moderation/<email>", methods=["GET", "POST"])
    @deps["login_required"]
    def admin_moderation_page(email):
        admin_user = deps["find_user_by_email"](email)
        if admin_user is None:
            return "User not found", 404

        if not deps["is_admin_email"](admin_user.email):
            deps["log_security_event"]("admin_moderation_denied", admin_user.email, "HTML moderation access denied")
            return deps["simple_page"](
                "Доступ закрыт",
                "Эта страница доступна только администраторам.",
                admin_user.email,
            ), 403

        if request.method == "POST":
            deps["validate_csrf_token"]()
            report_id = deps["clean_text"](request.form.get("report_id", ""))[:160]
            status = deps["clean_text"](request.form.get("status", "reviewing"))[:20]
            note = deps["clean_text"](request.form.get("note", ""))[:2000]
            action = deps["clean_text"](request.form.get("action", ""))[:80]
            reports_data = deps["load_reports"]()
            try:
                deps["moderation_service"].update_report_status(
                    reports_data,
                    report_id,
                    status,
                    moderator_email=admin_user.email,
                    note=note,
                    action=action or status,
                )
                deps["save_reports"](reports_data)
                deps["log_security_event"](
                    "admin_report_status_updated",
                    admin_user.email,
                    f"report={report_id}; status={status}; action={action or status}",
                )
            except (ValueError, LookupError) as error:
                return deps["simple_page"]("Ошибка модерации", str(error), admin_user.email), 400
            return redirect(f"/admin/moderation/{admin_user.email}", code=303)

        status_filter = deps["clean_text"](request.args.get("status", ""))
        if status_filter not in VALID_STATUSES:
            status_filter = ""
        reports_data = deps["load_reports"]()
        summary = deps["moderation_service"].summarize_reports(reports_data)
        raw_reports = deps["moderation_service"].list_reports(reports_data, status=status_filter)
        reports = []
        for report in raw_reports:
            status = report.get("status", "new")
            if status not in VALID_STATUSES:
                status = "new"
            reports.append({
                "id": report.get("id", ""),
                "reporter_email": report.get("reporter_email", ""),
                "target_email": report.get("target_email", ""),
                "reason": report.get("reason", ""),
                "details": report.get("details", ""),
                "status": status,
                "created_at": report.get("created_at", ""),
                "reviewed_by": report.get("reviewed_by", ""),
                "reviewed_at": report.get("reviewed_at", ""),
                "moderation_note": report.get("moderation_note", ""),
                "action": report.get("action", ""),
            })
        deps["log_security_event"]("admin_moderation_opened", admin_user.email, f"status={status_filter or 'all'}")
        ui, copy = page_copy(admin_user)
        filters = [{"value": "", "label": copy["all"]}] + [
            {"value": status, "label": copy[status]} for status in VALID_STATUSES
        ]
        return render_template(
            "admin_moderation.html",
            ui=ui,
            copy=copy,
            email=admin_user.email,
            reports=reports,
            summary=summary,
            filters=filters,
            statuses=VALID_STATUSES,
            status_filter=status_filter,
            csrf_token_input=deps["csrf_input"](),
        )

    return admin_routes
