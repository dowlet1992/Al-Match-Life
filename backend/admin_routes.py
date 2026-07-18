from flask import Blueprint, redirect, request


def create_admin_routes(deps):
    admin_routes = Blueprint("admin_routes", __name__)

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
            report_id = deps["clean_text"](request.form.get("report_id", ""))
            status = deps["clean_text"](request.form.get("status", "reviewing"))
            note = deps["clean_text"](request.form.get("note", ""))
            action = deps["clean_text"](request.form.get("action", ""))
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

            return redirect(f"/admin/moderation/{deps['safe_text'](admin_user.email)}")

        status_filter = deps["clean_text"](request.args.get("status", ""))
        reports_data = deps["load_reports"]()
        summary = deps["moderation_service"].summarize_reports(reports_data)
        reports = deps["moderation_service"].list_reports(reports_data, status=status_filter)
        deps["log_security_event"]("admin_moderation_opened", admin_user.email, f"status={status_filter or 'all'}")

        return render_admin_moderation_page(
            admin_user,
            reports,
            summary,
            status_filter,
            deps,
        )

    return admin_routes


def render_admin_moderation_page(admin_user, reports, summary, status_filter, deps):
    safe_text = deps["safe_text"]
    status_options = [
        ("", "Все"),
        ("new", "Новые"),
        ("reviewing", "В проверке"),
        ("resolved", "Решены"),
        ("dismissed", "Отклонены"),
    ]
    filter_links = ""
    for value, label in status_options:
        active_class = "active" if value == status_filter else ""
        href = f"/admin/moderation/{safe_text(admin_user.email)}"
        if value:
            href += f"?status={safe_text(value)}"
        filter_links += f'<a class="filter {active_class}" href="{href}">{safe_text(label)}</a>'

    cards_html = ""
    for report in reports:
        report_id = safe_text(report.get("id", ""))
        reporter_email = safe_text(report.get("reporter_email", ""))
        target_email = safe_text(report.get("target_email", ""))
        reason = safe_text(report.get("reason", ""))
        details = safe_text(report.get("details", ""))
        status = safe_text(report.get("status", "new"))
        created_at = safe_text(report.get("created_at", ""))
        reviewed_by = safe_text(report.get("reviewed_by", ""))
        reviewed_at = safe_text(report.get("reviewed_at", ""))
        moderation_note = safe_text(report.get("moderation_note", ""))
        action = safe_text(report.get("action", ""))

        cards_html += f"""
        <article class="report-card">
            <div class="report-top">
                <div>
                    <div class="report-id">#{report_id}</div>
                    <h2>{reason or "Жалоба"}</h2>
                </div>
                <span class="badge {status}">{status}</span>
            </div>
            <div class="meta-grid">
                <div><span>Reporter</span><strong>{reporter_email}</strong></div>
                <div><span>Target</span><strong>{target_email}</strong></div>
                <div><span>Created</span><strong>{created_at}</strong></div>
                <div><span>Reviewed</span><strong>{reviewed_by or "—"} {reviewed_at or ""}</strong></div>
            </div>
            <p class="details">{details or "Комментарий не указан."}</p>
            <div class="review-note">
                <span>Last action</span>
                <strong>{action or "—"}</strong>
                <p>{moderation_note or "Заметки модератора пока нет."}</p>
            </div>
            <form method="POST" class="review-form">
                {deps["csrf_input"]()}
                <input type="hidden" name="report_id" value="{report_id}">
                <select name="status">
                    <option value="reviewing" {"selected" if status == "reviewing" else ""}>В проверке</option>
                    <option value="resolved" {"selected" if status == "resolved" else ""}>Решено</option>
                    <option value="dismissed" {"selected" if status == "dismissed" else ""}>Отклонено</option>
                    <option value="new" {"selected" if status == "new" else ""}>Новое</option>
                </select>
                <input name="action" placeholder="Действие" value="{action}">
                <textarea name="note" placeholder="Заметка модератора">{moderation_note}</textarea>
                <button type="submit">Сохранить</button>
            </form>
        </article>
        """

    if not cards_html:
        cards_html = """
        <section class="empty-state">
            <h2>Жалоб нет</h2>
            <p>По выбранному фильтру ничего не найдено.</p>
        </section>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Moderation</title>
        <style>
            *{{box-sizing:border-box;}}
            body{{margin:0;background:#0b1020;color:#e5e7eb;font-family:Arial,sans-serif;}}
            .shell{{max-width:1180px;margin:0 auto;padding:24px;}}
            .topbar{{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:22px;}}
            .back{{color:white;text-decoration:none;background:#1f2937;border:1px solid #334155;border-radius:8px;padding:10px 12px;font-weight:bold;}}
            h1{{margin:0;font-size:30px;letter-spacing:0;}}
            .subtitle{{color:#94a3b8;margin:7px 0 0 0;}}
            .stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px;}}
            .stat{{background:#111827;border:1px solid #263244;border-radius:8px;padding:16px;}}
            .stat span{{display:block;color:#94a3b8;font-size:13px;margin-bottom:8px;}}
            .stat strong{{font-size:24px;}}
            .filters{{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px 0;}}
            .filter{{color:#cbd5e1;text-decoration:none;border:1px solid #334155;border-radius:8px;padding:9px 11px;background:#111827;}}
            .filter.active{{background:#2563eb;border-color:#2563eb;color:white;}}
            .reports{{display:grid;gap:14px;}}
            .report-card{{background:#111827;border:1px solid #263244;border-radius:8px;padding:18px;}}
            .report-top{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:14px;}}
            .report-id{{color:#94a3b8;font-size:13px;margin-bottom:5px;}}
            h2{{margin:0;font-size:20px;}}
            .badge{{display:inline-flex;align-items:center;border-radius:999px;padding:7px 10px;font-size:12px;font-weight:bold;text-transform:uppercase;background:#334155;color:#e5e7eb;}}
            .badge.new{{background:#7f1d1d;color:#fecaca;}}
            .badge.reviewing{{background:#78350f;color:#fde68a;}}
            .badge.resolved{{background:#064e3b;color:#a7f3d0;}}
            .badge.dismissed{{background:#312e81;color:#c7d2fe;}}
            .meta-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px;}}
            .meta-grid div,.review-note{{background:#0b1020;border:1px solid #1f2937;border-radius:8px;padding:11px;min-width:0;}}
            .meta-grid span,.review-note span{{display:block;color:#94a3b8;font-size:12px;margin-bottom:5px;}}
            .meta-grid strong{{display:block;overflow-wrap:anywhere;font-size:13px;}}
            .details{{line-height:1.5;color:#cbd5e1;margin:0 0 12px 0;}}
            .review-note{{margin-bottom:12px;}}
            .review-note p{{margin:7px 0 0 0;color:#cbd5e1;line-height:1.45;}}
            .review-form{{display:grid;grid-template-columns:160px 1fr;gap:10px;}}
            select,input,textarea{{width:100%;background:#0b1020;color:white;border:1px solid #334155;border-radius:8px;padding:11px;font:inherit;}}
            textarea{{grid-column:1/-1;min-height:82px;resize:vertical;}}
            button{{grid-column:1/-1;background:#16a34a;color:white;border:none;border-radius:8px;padding:12px 14px;font-weight:bold;cursor:pointer;}}
            .empty-state{{background:#111827;border:1px solid #263244;border-radius:8px;padding:28px;text-align:center;}}
            .empty-state p{{color:#94a3b8;}}
            @media(max-width:760px){{
                .shell{{padding:16px;}}
                .topbar{{align-items:flex-start;flex-direction:column;}}
                .stats,.meta-grid,.review-form{{grid-template-columns:1fr;}}
                h1{{font-size:25px;}}
            }}
        </style>
    </head>
    <body>
        <main class="shell">
            <div class="topbar">
                <div>
                    <h1>Moderation</h1>
                    <p class="subtitle">Жалобы, статусы и действия модерации</p>
                </div>
                <a class="back" href="/dashboard/{safe_text(admin_user.email)}">Dashboard</a>
            </div>
            <section class="stats">
                <div class="stat"><span>Total</span><strong>{summary.get("total", 0)}</strong></div>
                <div class="stat"><span>Open</span><strong>{summary.get("open", 0)}</strong></div>
                <div class="stat"><span>New</span><strong>{summary.get("by_status", {}).get("new", 0)}</strong></div>
                <div class="stat"><span>Resolved</span><strong>{summary.get("by_status", {}).get("resolved", 0)}</strong></div>
            </section>
            <nav class="filters">{filter_links}</nav>
            <section class="reports">{cards_html}</section>
        </main>
    </body>
    </html>
    """
