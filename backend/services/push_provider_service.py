import json
import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PushResult:
    outcome: str
    error_code: str = ""
    retry_after: int = 0


def provider_readiness(environ=None):
    env = environ or os.environ
    return {
        "android": bool(env.get("GOOGLE_APPLICATION_CREDENTIALS") and env.get("FCM_PROJECT_ID")),
        "ios": all(env.get(key) for key in ("APNS_KEY_ID", "APNS_TEAM_ID", "APNS_VOIP_TOPIC", "APNS_PRIVATE_KEY_FILE")),
        "web": all(env.get(key) for key in ("VAPID_PRIVATE_KEY_FILE", "VAPID_PUBLIC_KEY", "VAPID_SUBJECT")),
    }


def backoff_seconds(attempt, minimum=5, maximum=300):
    return min(maximum, max(minimum, minimum * (2 ** max(int(attempt) - 1, 0))))


def classify_http(platform, status, reason="", retry_after=0):
    reason = str(reason or "")
    if 200 <= int(status) < 300:
        return PushResult("delivered")
    invalid = (
        platform == "android" and reason in {"UNREGISTERED", "registration-token-not-registered"}
    ) or (
        platform == "ios" and (int(status) == 410 or reason in {"BadDeviceToken", "DeviceTokenNotForTopic", "ExpiredToken", "Unregistered"})
    ) or (platform == "web" and int(status) in {404, 410})
    if invalid:
        return PushResult("invalid_token", reason or str(status))
    if int(status) == 429 or int(status) >= 500:
        try:
            retry_seconds = max(int(retry_after or 0), 0)
        except (TypeError, ValueError):
            retry_seconds = 0
        return PushResult("retry", reason or str(status), retry_seconds)
    return PushResult("permanent_failure", reason or str(status))


def deliver(device, job, environ=None):
    platform = str(device.get("platform", ""))
    if not provider_readiness(environ).get(platform):
        return PushResult("provider_unconfigured", f"{platform}_unconfigured")
    if platform == "android":
        return _deliver_fcm(device, job, environ)
    if platform == "ios":
        return _deliver_apns(device, job, environ)
    if platform == "web":
        return _deliver_webpush(device, job, environ)
    return PushResult("permanent_failure", "unsupported_platform")


def _delivery_payload(job):
    payload = job.get("payload", {}) if isinstance(job.get("payload"), dict) else {}
    result = {key: str(value) for key, value in payload.items() if key in {"call_id", "call_type", "caller_email", "receiver_email"}}
    result["event_id"] = str(job.get("event_id", ""))
    result["event_type"] = str(job.get("event_type", "incoming_call"))
    result["expires_at"] = str(int(_epoch(job.get("expires_at", time.time() + 45))))
    return result


def _epoch(value):
    return value.timestamp() if hasattr(value, "timestamp") else float(value)


def _deliver_fcm(device, job, environ):
    env = environ or os.environ
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app(credentials.ApplicationDefault(), {"projectId": env["FCM_PROJECT_ID"]})
        message = messaging.Message(
            token=device["token"], data=_delivery_payload(job),
            android=messaging.AndroidConfig(priority="high", ttl=__import__("datetime").timedelta(seconds=45)),
        )
        messaging.send(message)
        return PushResult("delivered")
    except Exception as error:
        code = str(getattr(error, "code", "") or getattr(error, "default_message", "") or type(error).__name__)
        normalized = "UNREGISTERED" if "unregistered" in code.lower() or "not-registered" in code.lower() else code
        status = 404 if normalized == "UNREGISTERED" else 503
        return classify_http("android", status, normalized)


def _deliver_apns(device, job, environ):
    env = environ or os.environ
    try:
        import httpx
        import jwt
        with open(env["APNS_PRIVATE_KEY_FILE"], "r", encoding="utf-8") as key_file:
            provider_token = jwt.encode({"iss": env["APNS_TEAM_ID"], "iat": int(time.time())}, key_file.read(), algorithm="ES256", headers={"kid": env["APNS_KEY_ID"]})
        host = "api.sandbox.push.apple.com" if env.get("APNS_USE_SANDBOX", "false").lower() == "true" else "api.push.apple.com"
        headers = {
            "authorization": f"bearer {provider_token}", "apns-topic": env["APNS_VOIP_TOPIC"],
            "apns-push-type": "voip", "apns-priority": "10",
            "apns-expiration": str(int(_epoch(job.get("expires_at", time.time())))),
            "apns-collapse-id": str((job.get("payload") or {}).get("call_id") or job.get("event_id", ""))[:64],
        }
        with httpx.Client(http2=True, timeout=10) as client:
            response = client.post(f"https://{host}/3/device/{device['token']}", headers=headers, json={"aps": {"content-available": 1}, **_delivery_payload(job)})
        reason = response.json().get("reason", "") if response.content else ""
        return classify_http("ios", response.status_code, reason, response.headers.get("retry-after", 0))
    except Exception as error:
        return PushResult("retry", type(error).__name__)


def _deliver_webpush(device, job, environ):
    env = environ or os.environ
    try:
        from pywebpush import WebPushException, webpush
        subscription = json.loads(device["token"])
        with open(env["VAPID_PRIVATE_KEY_FILE"], "r", encoding="utf-8") as key_file:
            webpush(subscription_info=subscription, data=json.dumps(_delivery_payload(job)), vapid_private_key=key_file.read(), vapid_claims={"sub": env["VAPID_SUBJECT"]}, ttl=45)
        return PushResult("delivered")
    except Exception as error:
        response = getattr(error, "response", None)
        if response is not None:
            return classify_http("web", response.status_code, "webpush_rejected", response.headers.get("retry-after", 0))
        return PushResult("retry", type(error).__name__)
