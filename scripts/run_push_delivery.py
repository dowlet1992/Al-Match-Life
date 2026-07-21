#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.repositories.call_push_outbox_repository import get_call_push_outbox_repository
from backend.services import push_delivery_worker, push_provider_service


def build_report(apply=False, batch_size=50, now=None, environ=None, repository=None):
    now = float(now if now is not None else time.time())
    readiness = push_provider_service.provider_readiness(environ)
    repository = repository or get_call_push_outbox_repository()
    base = {"mode": "apply" if apply else "dry-run", "batch_size": batch_size, "providers": readiness}
    if repository is None:
        return {**base, "blockers": ["Push delivery worker requires PostgreSQL storage."]}
    if not apply:
        return {**base, "due_jobs": repository.dry_run_count(now), "mutations_applied": False, "blockers": []}
    return {**base, **push_delivery_worker.run_batch(repository, now, batch_size=batch_size, environ=environ), "blockers": []}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Deliver one bounded incoming-call push batch.")
    parser.add_argument("--apply", action="store_true", help="Claim and deliver jobs; default is dry-run.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 500:
        parser.error("--batch-size must be between 1 and 500")
    report = build_report(args.apply, args.batch_size)
    print(json.dumps(report, indent=2 if args.pretty else None, sort_keys=True))
    return 1 if report.get("blockers") else 0


if __name__ == "__main__":
    raise SystemExit(main())
