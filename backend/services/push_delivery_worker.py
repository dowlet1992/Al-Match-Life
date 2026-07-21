from datetime import datetime, timezone

from backend.services import push_provider_service


MAX_ATTEMPTS = 5


def run_batch(repository, now, batch_size=50, deliver=None, environ=None):
    deliver = deliver or push_provider_service.deliver
    jobs = repository.claim_due(now, batch_size=batch_size)
    report = {"claimed": len(jobs), "delivered": 0, "retried": 0, "failed": 0, "expired_tokens": 0}
    for job in jobs:
        devices = repository.prepare_devices(job["event_id"], job["target_user_id"], now)
        for device in devices:
            try:
                result = deliver(device, job, environ=environ)
            except Exception as error:
                result = push_provider_service.PushResult("retry", type(error).__name__)
            if result.outcome == "invalid_token":
                repository.revoke_token(device["token_hash"])
                repository.finish_device(job["event_id"], device["device_id"], "invalid_token", result.error_code)
                report["expired_tokens"] += 1
            elif result.outcome == "delivered":
                repository.finish_device(job["event_id"], device["device_id"], "delivered")
            elif result.outcome in {"retry", "provider_unconfigured"}:
                attempts = int(device.get("delivery_attempts", 0) or 0) + 1
                expires_at = job.get("expires_at")
                expiry_epoch = expires_at.timestamp() if hasattr(expires_at, "timestamp") else float(expires_at)
                retry_delay = result.retry_after or push_provider_service.backoff_seconds(attempts)
                if attempts < MAX_ATTEMPTS and float(now) + retry_delay < expiry_epoch:
                    available_at = datetime.fromtimestamp(float(now) + retry_delay, tz=timezone.utc)
                    repository.finish_device(job["event_id"], device["device_id"], "pending", result.error_code, available_at)
                else:
                    repository.finish_device(job["event_id"], device["device_id"], "failed", result.error_code)
            else:
                repository.finish_device(job["event_id"], device["device_id"], "failed", result.error_code)

        summary = repository.delivery_summary(job["event_id"])
        if summary["pending"]:
            repository.finish(job["event_id"], "pending", "device_retry_pending", summary["next_available_at"])
            report["retried"] += 1
        elif summary["delivered"]:
            repository.finish(job["event_id"], "delivered")
            report["delivered"] += 1
        else:
            repository.finish(job["event_id"], "failed", "no_device_delivered")
            report["failed"] += 1
    return report
