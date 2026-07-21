from pathlib import Path


SETTINGS = Path("frontend/settings.html").read_text(encoding="utf-8")


def test_settings_has_explicit_push_permission_controls():
    assert 'id="enablePushCalls"' in SETTINGS
    assert 'id="disablePushCalls"' in SETTINGS
    assert "Notification.requestPermission()" in SETTINGS
    assert "pushManager.subscribe" in SETTINGS


def test_settings_registers_subscription_with_csrf_and_can_revoke():
    assert "'/api/push/config'" in SETTINGS
    assert "'/api/push/devices'" in SETTINGS
    assert "'X-CSRF-Token'" in SETTINGS
    assert "subscription.unsubscribe()" in SETTINGS


def test_service_worker_closes_cancelled_call_notification_by_call_id():
    worker = Path("static/push-service-worker.js").read_text(encoding="utf-8")
    assert "call_cancelled" in worker
    assert "getNotifications({ tag: callTag })" in worker
    assert "notification.close()" in worker
