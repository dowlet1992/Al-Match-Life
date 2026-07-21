#!/usr/bin/env python3
"""Run a bounded, one-shot call maintenance pass; dry-run unless --apply is set."""

import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.repositories.call_signal_repository import timeout_transition


def build_report(*, apply=False, now=None, batch_size=200, load_rooms=None, run_maintenance=None):
    now = float(now if now is not None else time.time())
    batch_size = min(max(int(batch_size), 1), 1000)
    if apply:
        if run_maintenance is None:
            from app import run_call_maintenance
        counts = run_maintenance(now=now, batch_size=batch_size)
        return {"mode": "apply", "batch_size": batch_size, **counts}

    if load_rooms is None:
        from backend.call_signals_store import load_call_signals
        load_rooms = load_call_signals
    rooms = load_rooms()
    due_count = sum(
        timeout_transition(room_id, room, now) is not None
        for room_id, room in rooms.items()
        if isinstance(room, dict)
    )
    return {
        "mode": "dry-run",
        "batch_size": batch_size,
        "due_call_rooms": min(due_count, batch_size),
        "mutations_applied": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect or apply one call-maintenance batch.")
    parser.add_argument("--apply", action="store_true", help="Apply mutations; default is dry-run.")
    parser.add_argument("--batch-size", type=int, default=200, help="Maximum rooms per pass (1-1000).")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the PII-free JSON report.")
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 1000:
        parser.error("--batch-size must be between 1 and 1000")
    report = build_report(apply=args.apply, batch_size=args.batch_size)
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
