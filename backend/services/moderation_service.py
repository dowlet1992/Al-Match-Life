from datetime import datetime, timezone
from secrets import token_urlsafe


VALID_REPORT_STATUSES = {"new", "reviewing", "resolved", "dismissed"}
OPEN_REPORT_STATUSES = {"new", "reviewing"}


def normalize_email(value):
    return str(value or "").strip().lower()


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean_value(value, limit=1000):
    value = str(value or "").strip()
    return value[:limit]


def create_profile_report(reporter_email, target_email, reason, details, report_id=None, created_at=None):
    return {
        "id": report_id or token_urlsafe(10),
        "reporter_email": normalize_email(reporter_email),
        "target_email": normalize_email(target_email),
        "reason": clean_value(reason, 120) or "other",
        "details": clean_value(details, 2000),
        "status": "new",
        "created_at": created_at or utc_timestamp(),
        "updated_at": "",
        "reviewed_by": "",
        "reviewed_at": "",
        "moderation_note": "",
        "action": "",
    }


def list_reports(reports_data, status=None, reporter_email=None, target_email=None):
    reports = reports_data.get("reports", []) if isinstance(reports_data, dict) else []
    status = clean_value(status, 40)
    reporter_email = normalize_email(reporter_email)
    target_email = normalize_email(target_email)

    filtered = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        if status and report.get("status") != status:
            continue
        if reporter_email and normalize_email(report.get("reporter_email")) != reporter_email:
            continue
        if target_email and normalize_email(report.get("target_email")) != target_email:
            continue
        filtered.append(report)

    return sorted(filtered, key=lambda item: str(item.get("created_at", "")), reverse=True)


def summarize_reports(reports_data):
    reports = list_reports(reports_data)
    by_status = {status: 0 for status in sorted(VALID_REPORT_STATUSES)}
    for report in reports:
        status = report.get("status", "new")
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total": len(reports),
        "open": sum(by_status.get(status, 0) for status in OPEN_REPORT_STATUSES),
        "by_status": by_status,
    }


def update_report_status(reports_data, report_id, status, moderator_email="", note="", action=""):
    if status not in VALID_REPORT_STATUSES:
        raise ValueError(f"Unsupported report status: {status}")

    if not isinstance(reports_data, dict) or not isinstance(reports_data.get("reports"), list):
        reports_data = {"reports": []}

    report_id = str(report_id or "")
    for report in reports_data["reports"]:
        if not isinstance(report, dict) or str(report.get("id", "")) != report_id:
            continue

        now = utc_timestamp()
        report["status"] = status
        report["updated_at"] = now
        report["reviewed_by"] = normalize_email(moderator_email)
        report["reviewed_at"] = now
        report["moderation_note"] = clean_value(note, 2000)
        report["action"] = clean_value(action, 80)
        return report

    raise LookupError(f"Report not found: {report_id}")


def mark_report_reviewing(reports_data, report_id, moderator_email="", note=""):
    return update_report_status(
        reports_data,
        report_id,
        "reviewing",
        moderator_email=moderator_email,
        note=note,
        action="review",
    )


def resolve_report(reports_data, report_id, moderator_email="", note="", action="resolved"):
    return update_report_status(
        reports_data,
        report_id,
        "resolved",
        moderator_email=moderator_email,
        note=note,
        action=action,
    )


def dismiss_report(reports_data, report_id, moderator_email="", note=""):
    return update_report_status(
        reports_data,
        report_id,
        "dismissed",
        moderator_email=moderator_email,
        note=note,
        action="dismissed",
    )
