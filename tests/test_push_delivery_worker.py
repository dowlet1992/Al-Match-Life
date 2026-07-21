from datetime import datetime, timezone
import inspect

from backend.repositories.call_push_outbox_repository import PostgresCallPushOutboxRepository
from backend.services import push_delivery_worker, push_provider_service
from scripts.run_push_delivery import build_report


class MemoryRepository:
    def __init__(self, jobs, devices):
        self.jobs, self.devices, self.finished, self.revoked, self.device_finished = jobs, devices, [], [], []
        self.states = {item["device_id"]: {"status": "pending", "available_at": 0} for item in devices}
    def claim_due(self, now, batch_size=50): return self.jobs[:batch_size]
    def prepare_devices(self, event_id, target, now):
        return [{**item, "delivery_attempts": sum(1 for call in self.device_finished if call[1] == item["device_id"])}
                for item in self.devices if self.states[item["device_id"]]["status"] == "pending"
                and self.states[item["device_id"]]["available_at"] <= now]
    def finish_device(self, event_id, device_id, status, error_code="", available_at=None):
        self.device_finished.append((event_id, device_id, status, error_code, available_at))
        self.states[device_id] = {"status": status, "available_at": available_at.timestamp() if available_at else 0}
    def delivery_summary(self, event_id):
        states = list(self.states.values())
        pending = [item for item in states if item["status"] == "pending"]
        return {"pending": len(pending), "delivered": sum(item["status"] == "delivered" for item in states),
                "failed": sum(item["status"] in {"failed", "invalid_token"} for item in states),
                "next_available_at": datetime.fromtimestamp(min(item["available_at"] for item in pending), tz=timezone.utc) if pending else None}
    def finish(self, *args): self.finished.append(args)
    def revoke_token(self, token_hash): self.revoked.append(token_hash)
    def dry_run_count(self, now): return len(self.jobs)


def job(attempts=1, expires=200):
    return {"event_id": "event", "target_user_id": "user", "payload": {}, "attempts": attempts,
            "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc)}


def device(platform="android"):
    return {"platform": platform, "token": "secret", "token_hash": f"hash-{platform}", "device_id": f"device-{platform}"}


def test_provider_readiness_never_returns_secrets():
    env = {"GOOGLE_APPLICATION_CREDENTIALS": "/secret/key.json", "FCM_PROJECT_ID": "project"}
    assert push_provider_service.provider_readiness(env) == {"android": True, "ios": False, "web": False}
    assert "secret" not in str(push_provider_service.provider_readiness(env))


def test_provider_response_classification_revokes_only_definitive_tokens():
    assert push_provider_service.classify_http("android", 404, "UNREGISTERED").outcome == "invalid_token"
    assert push_provider_service.classify_http("ios", 410, "Unregistered").outcome == "invalid_token"
    assert push_provider_service.classify_http("web", 410).outcome == "invalid_token"
    assert push_provider_service.classify_http("android", 503, "UNAVAILABLE").outcome == "retry"
    assert push_provider_service.classify_http("ios", 403, "InvalidProviderToken").outcome == "permanent_failure"


def test_native_providers_preserve_cancellation_and_collapse_by_call():
    payload = push_provider_service._delivery_payload({
        "event_id": "cancel-event", "event_type": "call_cancelled", "expires_at": 200,
        "payload": {"call_id": "stable-call", "call_type": "audio"},
    })
    assert payload["event_type"] == "call_cancelled"
    assert payload["call_id"] == "stable-call"
    fcm_source = inspect.getsource(push_provider_service._deliver_fcm)
    apns_source = inspect.getsource(push_provider_service._deliver_apns)
    assert '"event_type": "incoming_call"' not in fcm_source
    assert 'get("call_id") or job.get("event_id"' in apns_source


def test_worker_delivers_once_and_revokes_invalid_sibling_token():
    repository = MemoryRepository([job()], [device(), device("ios")])
    outcomes = iter((push_provider_service.PushResult("delivered"), push_provider_service.PushResult("invalid_token", "Unregistered")))
    report = push_delivery_worker.run_batch(repository, 100, deliver=lambda *args, **kwargs: next(outcomes))
    assert report == {"claimed": 1, "delivered": 1, "retried": 0, "failed": 0, "expired_tokens": 1}
    assert repository.finished == [("event", "delivered")]
    assert repository.revoked == ["hash-ios"]
    assert [item[2] for item in repository.device_finished] == ["delivered", "invalid_token"]


def test_worker_retries_temporary_failure_with_backoff():
    repository = MemoryRepository([job(expires=500)], [device()])
    result = push_provider_service.PushResult("retry", "UNAVAILABLE", 60)
    report = push_delivery_worker.run_batch(repository, 100, deliver=lambda *args, **kwargs: result)
    assert report["retried"] == 1
    assert repository.finished[0][1:3] == ("pending", "device_retry_pending")
    assert repository.finished[0][3].timestamp() == 160


def test_worker_fails_when_retry_would_miss_call_expiry():
    repository = MemoryRepository([job(expires=120)], [device()])
    result = push_provider_service.PushResult("retry", "UNAVAILABLE", 60)
    assert push_delivery_worker.run_batch(repository, 100, deliver=lambda *args, **kwargs: result)["failed"] == 1
    assert repository.finished[0][1] == "failed"


def test_worker_does_not_resend_device_already_delivered():
    repository = MemoryRepository([job(expires=500)], [device(), device("ios")])
    first = iter((push_provider_service.PushResult("delivered"), push_provider_service.PushResult("retry", "busy", 10)))
    assert push_delivery_worker.run_batch(repository, 100, deliver=lambda *args, **kwargs: next(first))["retried"] == 1
    second_devices = []
    def second_delivery(selected, selected_job, **kwargs):
        second_devices.append(selected["device_id"])
        return push_provider_service.PushResult("delivered")
    assert push_delivery_worker.run_batch(repository, 110, deliver=second_delivery)["delivered"] == 1
    assert second_devices == ["device-ios"]


def test_delivery_cli_report_is_dry_run_and_pii_free():
    repository = MemoryRepository([job()], [])
    report = build_report(False, now=100, repository=repository, environ={})
    assert report["due_jobs"] == 1
    assert report["mutations_applied"] is False
    assert "event" not in str(report)


class FakeCursor:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, query, params=None): self.calls.append((query, params))
    def fetchall(self): return []
class FakeConnection:
    def __init__(self): self.value, self.committed = FakeCursor(), False
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def cursor(self): return self.value
    def commit(self): self.committed = True
class FakeClient:
    def __init__(self): self.connection = FakeConnection()
    def connect(self): return self.connection


def test_postgres_claim_recovers_stale_locks_and_uses_skip_locked():
    client = FakeClient()
    assert PostgresCallPushOutboxRepository(client).claim_due(100) == []
    queries = [query for query, _ in client.connection.value.calls]
    assert any("locked_at <" in query for query in queries)
    assert any("FOR UPDATE SKIP LOCKED" in query for query in queries)
    assert client.connection.committed is True
