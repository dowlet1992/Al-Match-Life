import pytest

from backend.services import moderation_service


def test_create_profile_report_normalizes_and_sets_new_status():
    report = moderation_service.create_profile_report(
        "Alice@Example.com",
        "Bob@Example.com",
        "Spam",
        "Message details",
        report_id="report-1",
        created_at="2026-01-01 10:00:00",
    )

    assert report["id"] == "report-1"
    assert report["reporter_email"] == "alice@example.com"
    assert report["target_email"] == "bob@example.com"
    assert report["status"] == "new"
    assert report["reviewed_by"] == ""


def test_list_reports_filters_and_sorts_newest_first():
    reports_data = {"reports": [
        {"id": "old", "status": "new", "target_email": "bob@example.com", "created_at": "2026-01-01 10:00:00"},
        {"id": "new", "status": "new", "target_email": "bob@example.com", "created_at": "2026-01-02 10:00:00"},
        {"id": "other", "status": "resolved", "target_email": "carol@example.com", "created_at": "2026-01-03 10:00:00"},
    ]}

    reports = moderation_service.list_reports(reports_data, status="new", target_email="BOB@example.com")

    assert [report["id"] for report in reports] == ["new", "old"]


def test_summarize_reports_counts_open_statuses():
    summary = moderation_service.summarize_reports({"reports": [
        {"status": "new"},
        {"status": "reviewing"},
        {"status": "resolved"},
    ]})

    assert summary["total"] == 3
    assert summary["open"] == 2
    assert summary["by_status"]["resolved"] == 1


def test_update_report_status_sets_moderation_metadata():
    reports_data = {"reports": [{"id": "report-1", "status": "new"}]}

    updated = moderation_service.resolve_report(
        reports_data,
        "report-1",
        moderator_email="Admin@Example.com",
        note="Handled",
        action="warning_sent",
    )

    assert updated["status"] == "resolved"
    assert updated["reviewed_by"] == "admin@example.com"
    assert updated["moderation_note"] == "Handled"
    assert updated["action"] == "warning_sent"
    assert updated["reviewed_at"]


def test_update_report_status_rejects_unknown_status():
    with pytest.raises(ValueError):
        moderation_service.update_report_status({"reports": []}, "missing", "bad")


def test_update_report_status_requires_existing_report():
    with pytest.raises(LookupError):
        moderation_service.resolve_report({"reports": []}, "missing")
