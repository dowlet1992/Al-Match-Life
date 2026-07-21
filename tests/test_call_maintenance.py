import json
import subprocess
import sys

import app
from scripts.run_call_maintenance import build_report


def test_call_maintenance_dry_run_has_no_mutations_or_identifiers():
    rooms = {
        "private-room-id": {"status": "ringing", "messages": [{
            "type": "ringing", "from": "secret@example.com", "to": "other@example.com",
            "created_at": 1, "payload": {"call_type": "video"},
        }]},
    }

    report = build_report(apply=False, now=100, load_rooms=lambda: rooms)
    serialized = json.dumps(report)

    assert report == {"mode": "dry-run", "batch_size": 200, "due_call_rooms": 1, "mutations_applied": False}
    assert "private-room-id" not in serialized
    assert "secret@example.com" not in serialized


def test_call_maintenance_apply_delegates_one_bounded_pass():
    calls = []

    def run_maintenance(**options):
        calls.append(options)
        return {"expired_call_rooms": 2, "call_history_events": 2,
                "pruned_call_rooms": 1, "expired_rate_limit_buckets": 4}

    report = build_report(apply=True, now=100, batch_size=50, run_maintenance=run_maintenance)

    assert calls == [{"now": 100.0, "batch_size": 50}]
    assert report["mode"] == "apply"
    assert report["expired_call_rooms"] == 2


def test_app_call_maintenance_records_transitions_and_returns_counts(monkeypatch):
    monkeypatch.setattr(app, "expire_due_call_rooms", lambda now, **options: [{"transition": {
        "type": "missed", "from": "a@test.com", "to": "b@test.com",
        "payload": {"call_type": "video"},
    }}])
    recorded = []
    monkeypatch.setattr(app, "record_call_chat_event", lambda *args: recorded.append(args) or True)
    monkeypatch.setattr(app, "prune_expired_call_rooms", lambda **options: 3)

    report = app.run_call_maintenance(now=100, batch_size=10)

    assert recorded == [("a@test.com", "b@test.com", "video", "missed")]
    assert report == {"expired_call_rooms": 1, "call_history_events": 1,
                      "pruned_call_rooms": 3, "expired_rate_limit_buckets": 0}


def test_call_maintenance_real_cli_dry_run_starts_without_mutation():
    result = subprocess.run(
        [sys.executable, "scripts/run_call_maintenance.py"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["mode"] == "dry-run"
    assert report["mutations_applied"] is False
