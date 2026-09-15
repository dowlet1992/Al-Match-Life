from scripts.release_gate import build_release_gate_report, dependency_health, guarded_report


def test_release_gate_passes_only_when_every_required_gate_passes():
    report = build_release_gate_report(
        config_report={"ready_for_production": True},
        backup_report={"ready": True},
        media_backup_report={"ready": True},
        security_report={"ok": True},
        dependencies_report={"ok": True},
    )

    assert report["ready_for_release"] is True
    assert report["blockers"] == []


def test_release_gate_reports_stable_machine_readable_blockers():
    report = build_release_gate_report(
        config_report={"ready_for_production": False},
        backup_report={"ready": True},
        media_backup_report={"ready": True},
        security_report={"ok": False},
        dependencies_report={"ok": True},
    )

    assert report["ready_for_release"] is False
    assert report["blockers"] == ["production_configuration", "security_headers_and_auth"]


def test_dependency_health_does_not_expose_command_output():
    class Result:
        returncode = 1
        stdout = "package secret conflict"
        stderr = "private path"

    calls = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    report = dependency_health(runner=runner)

    assert report == {"ok": False, "summary": "dependency_conflicts_found"}
    assert calls[0][0][-2:] == ["pip", "check"]
    assert calls[0][1]["timeout"] == 60


def test_guarded_release_check_reports_only_exception_type():
    def failing_check():
        raise RuntimeError("postgresql://user:secret@private-host/database")

    report = guarded_report(failing_check, {"ok": False, "summary": "check_failed"})

    assert report == {
        "ok": False,
        "summary": "check_failed",
        "check_error_type": "RuntimeError",
    }
    assert "secret" not in str(report)
