from pathlib import Path


SETTINGS = Path("frontend/settings.html").read_text(encoding="utf-8")
SETTINGS_JS = Path("static/settings.js").read_text(encoding="utf-8")


def test_settings_has_explicit_push_permission_controls():
    assert 'id="enablePushCalls"' in SETTINGS
    assert 'id="disablePushCalls"' in SETTINGS
    assert "Notification.requestPermission()" in SETTINGS_JS
    assert "pushManager.subscribe" in SETTINGS_JS


def test_settings_registers_subscription_with_csrf_and_can_revoke():
    assert "'/api/push/config'" in SETTINGS_JS
    assert "'/api/push/devices'" in SETTINGS_JS
    assert "'X-CSRF-Token'" in SETTINGS_JS
    assert "subscription.unsubscribe()" in SETTINGS_JS


def test_settings_uses_external_assets_without_inline_code():
    assert "/static/settings.css" in SETTINGS
    assert "/static/settings.js" in SETTINGS
    assert "<style" not in SETTINGS
    assert "<script>" not in SETTINGS


def test_push_runtime_copy_comes_from_localized_template_data():
    assert 'data-enabling="{{ ui.push_enabling }}"' in SETTINGS
    assert "const copy = container ? container.dataset : {}" in SETTINGS_JS
    assert "text('enabled'" in SETTINGS_JS
    assert "(await response.json()).error" not in SETTINGS_JS


def test_service_worker_closes_cancelled_call_notification_by_call_id():
    worker = Path("static/push-service-worker.js").read_text(encoding="utf-8")
    assert "call_cancelled" in worker
    assert "getNotifications({ tag: callTag })" in worker
    assert "notification.close()" in worker
    assert "data.notification_body" in worker
    assert "data.notification_action" in worker
