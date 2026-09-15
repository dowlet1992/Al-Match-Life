import os

from backend.database import load_database_settings, mask_database_url, validate_database_settings
from backend.services.push_provider_service import provider_readiness


WEAK_SECRET_VALUES = {
    "",
    "change-me",
    "changeme",
    "secret",
    "dev",
    "development",
    "password",
    "dev-only-change-before-production-ai-match-life-secret",
}


def is_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_environment(environ=None, env_path=None):
    env = os.environ if environ is None else environ
    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")

    if not os.path.exists(env_path):
        return env

    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in env:
                env[key] = value

    return env


def parse_admin_emails(value):
    emails = set()
    for item in str(value or "").replace(";", ",").split(","):
        email = item.strip().lower()
        if email:
            emails.add(email)
    return emails


def is_admin_email(email, environ=None):
    environ = os.environ if environ is None else environ
    return str(email or "").strip().lower() in parse_admin_emails(environ.get("ADMIN_EMAILS", ""))


def is_production_environment(environ=None):
    environ = os.environ if environ is None else environ
    return (
        str(environ.get("FLASK_ENV", "")).strip().lower() == "production"
        or str(environ.get("APP_ENV", "")).strip().lower() == "production"
    )


def read_secret(environ, value_key, file_key):
    """Read a secret from the environment or an explicitly configured file."""
    value = str(environ.get(value_key, "")).strip()
    if value:
        return value
    secret_file = str(environ.get(file_key, "")).strip()
    if not secret_file:
        return ""
    try:
        with open(secret_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def has_secure_secret_key(environ=None):
    environ = os.environ if environ is None else environ
    secret = read_secret(environ, "FLASK_SECRET_KEY", "FLASK_SECRET_KEY_FILE")
    return len(secret) >= 32 and secret.lower() not in WEAK_SECRET_VALUES


def has_email_provider(environ=None):
    environ = os.environ if environ is None else environ
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]
    return all(str(environ.get(key, "")).strip() for key in required)


def has_sms_provider(environ=None):
    environ = os.environ if environ is None else environ
    required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID"]
    return all(str(environ.get(key, "")).strip() for key in required)


def has_turn_provider(environ=None):
    environ = os.environ if environ is None else environ
    return all(str(environ.get(key, "")).strip() for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"))


def build_production_readiness_report(environ=None):
    environ = os.environ if environ is None else environ
    database_settings = load_database_settings(environ)
    database_issues = validate_database_settings(database_settings)
    production = is_production_environment(environ)
    email_configured = has_email_provider(environ)
    sms_configured = has_sms_provider(environ)
    two_factor_enabled = is_truthy(environ.get("LOGIN_2FA_ENABLED"))
    ai_provider = str(environ.get("AI_PROVIDER", "ollama")).strip().lower()
    ai_provider_configured = ai_provider == "ollama" and bool(
        str(environ.get("OLLAMA_MODEL", "qwen2.5:7b")).strip()
    )

    turn_configured = has_turn_provider(environ)
    conference_configured = all(str(environ.get(key, "")).strip() for key in (
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
    )) and len(str(environ.get("LIVEKIT_API_SECRET", ""))) >= 16
    push_providers = provider_readiness(environ)
    checks = {
        "production_mode": production,
        "secure_secret_key": has_secure_secret_key(environ),
        "admin_emails_configured": bool(parse_admin_emails(environ.get("ADMIN_EMAILS", ""))),
        "database_config_valid": not database_issues,
        "postgres_enabled": database_settings.postgres_enabled,
        "json_data_encryption_configured": bool(str(environ.get("DATA_ENCRYPTION_KEY", "")).strip()),
        "email_provider_configured": email_configured,
        "sms_provider_configured": sms_configured,
        "verification_provider_configured": email_configured or sms_configured,
        "login_2fa_enabled": two_factor_enabled,
        "ai_provider_configured": ai_provider_configured,
        "openai_configured": bool(str(environ.get("OPENAI_API_KEY", "")).strip()),
        "turn_provider_configured": turn_configured,
        "conference_provider_configured": conference_configured,
        "push_providers": push_providers,
        "push_delivery_configured": any(push_providers.values()),
    }

    blockers = []
    warnings = []

    if not production:
        blockers.append("Production mode is not enabled; set FLASK_ENV=production or APP_ENV=production before deploy.")

    if production and not checks["secure_secret_key"]:
        blockers.append("FLASK_SECRET_KEY must be a strong unique value in production.")

    if production and not checks["admin_emails_configured"]:
        blockers.append("ADMIN_EMAILS must include at least one administrator in production.")

    if production and not database_settings.postgres_enabled:
        blockers.append("STORAGE_BACKEND should be postgres in production.")

    if production and not database_settings.postgres_enabled and not checks["json_data_encryption_configured"]:
        blockers.append("DATA_ENCRYPTION_KEY is required when production uses JSON storage.")

    blockers.extend(database_issues)

    if production and not checks["verification_provider_configured"]:
        blockers.append("Configure SMTP or Twilio before production account verification.")

    if production and not turn_configured:
        blockers.append("Configure Twilio Network Traversal credentials for reliable production calls.")

    if production and not any(push_providers.values()):
        blockers.append("Configure at least one FCM, APNs, or Web Push provider for production call delivery.")

    if not two_factor_enabled:
        warnings.append("LOGIN_2FA_ENABLED is disabled.")

    if not ai_provider_configured:
        warnings.append("Configure AI_PROVIDER=ollama and OLLAMA_MODEL for the local AI Assistant.")

    if not conference_configured:
        warnings.append("Configure LIVEKIT_URL, LIVEKIT_API_KEY, and a strong LIVEKIT_API_SECRET for group calls.")

    for platform, configured in push_providers.items():
        if not configured:
            warnings.append(f"Push provider for {platform} is not configured.")

    return {
        "ready_for_production": production and not blockers,
        "checks": checks,
        "storage_backend": database_settings.storage_backend,
        "database_url": mask_database_url(database_settings.database_url),
        "blockers": blockers,
        "warnings": warnings,
    }
