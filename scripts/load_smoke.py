import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
import app as application


def request_path(path, user_email=""):
    started = time.perf_counter()
    client = application.app.test_client()
    if user_email:
        with client.session_transaction() as session_data:
            session_data["user_email"] = user_email
    response = client.get(path)
    return response.status_code, (time.perf_counter() - started) * 1000


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0
    return ordered[min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))]


def benchmark(path, requests, concurrency, user_email=""):
    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(request_path, path, user_email) for _ in range(requests)]
        for future in as_completed(futures):
            results.append(future.result())
    durations = [duration for _status, duration in results]
    return {
        "path": path,
        "requests": len(results),
        "successes": sum(status in {200, 302, 304} for status, _duration in results),
        "status_codes": {str(code): sum(status == code for status, _ in results) for code in sorted({status for status, _ in results})},
        "median_ms": round(statistics.median(durations), 2),
        "p95_ms": round(percentile(durations, 0.95), 2),
        "max_ms": round(max(durations), 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only NOVIX application load smoke test")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    user = application.users[0] if application.users else None
    routes = [("/api/health", ""), ("/", "")]
    if user:
        routes.extend([
            (f"/dashboard/{user.id}", user.email),
            (f"/radar/{user.id}", user.email),
            (f"/messages/{user.id}", user.email),
            (f"/ai_copilot/{user.id}", user.email),
        ])
    reports = [benchmark(path, max(1, args.requests), max(1, args.concurrency), email) for path, email in routes]
    payload = {"ok": all(item["successes"] == item["requests"] for item in reports), "routes": reports}
    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    raise SystemExit(0 if payload["ok"] else 1)


if __name__ == "__main__":
    main()
