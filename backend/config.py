import os

from backend.database import load_database_settings, mask_database_url, validate_database_settings


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


def parse_admin_emails(value):
    emails = set()
    for item in str(value or "").replace(";", ",").split(","):
        email = item.strip().lower()
        if email:
            emails.add(email)
    return emails


def is_admin_email(email, environ=None):
    environ = environ or os.environ
    return str(email or "").strip().lower() in parse_admin_emails(environ.get("ADMIN_EMAILS", ""))


def is_production_environment(environ=None):
    environ = environ or os.environ
    return (
        str(environ.get("FLASK_ENV", "")).strip().lower() == "production"
        or str(environ.get("APP_ENV", "")).strip().lower() == "production"
    )


def has_secure_secret_key(environ=None):
    environ = environ or os.environ
    secret = str(environ.get("FLASK_SECRET_KEY", "")).strip()
    return len(secret) >= 32 and secret.lower() not in WEAK_SECRET_VALUES


def has_email_provider(environ=None):
    environ = environ or os.environ
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]
    return all(str(environ.get(key, "")).strip() for key in required)


def has_sms_provider(environ=None):
    environ = environ or os.environ
    required = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_VERIFY_SERVICE_SID"]
    return all(str(environ.get(key, "")).strip() for key in required)


def build_production_readiness_report(environ=None):
    environ = environ or os.environ
    database_settings = load_database_settings(environ)
    database_issues = validate_database_settings(database_settings)
    production = is_production_environment(environ)
    email_configured = has_email_provider(environ)
    sms_configured = has_sms_provider(environ)
    two_factor_enabled = is_truthy(environ.get("LOGIN_2FA_ENABLED"))
    openai_configured = bool(str(environ.get("OPENAI_API_KEY", "")).strip())

    checks = {
        "production_mode": production,
        "secure_secret_key": has_secure_secret_key(environ),
        "admin_emails_configured": bool(parse_admin_emails(environ.get("ADMIN_EMAILS", ""))),
        "database_config_valid": not database_issues,
        "postgres_enabled": database_settings.postgres_enabled,
        "email_provider_configured": email_configured,
        "sms_provider_configured": sms_configured,
        "verification_provider_configured": email_configured or sms_configured,
        "login_2fa_enabled": two_factor_enabled,
        "openai_configured": openai_configured,
    }

    blockers = []
    warnings = []

    if production and not checks["secure_secret_key"]:
        blockers.append("FLASK_SECRET_KEY must be a strong unique value in production.")

    if production and not checks["admin_emails_configured"]:
        blockers.append("ADMIN_EMAILS must include at least one administrator in production.")

    if production and not database_settings.postgres_enabled:
        blockers.append("STORAGE_BACKEND should be postgres in production.")

    blockers.extend(database_issues)

    if production and not checks["verification_provider_configured"]:
        blockers.append("Configure SMTP or Twilio before production account verification.")

    if not production:
        warnings.append("Production mode is not enabled; set FLASK_ENV=production or APP_ENV=production before deploy.")

    if not two_factor_enabled:
        warnings.append("LOGIN_2FA_ENABLED is disabled.")

    if not openai_configured:
        warnings.append("OPENAI_API_KEY is not configured; AI will use fallback behavior.")

    return {
        "ready_for_production": production and not blockers,
        "checks": checks,
        "storage_backend": database_settings.storage_backend,
        "database_url": mask_database_url(database_settings.database_url),
        "blockers": blockers,
        "warnings": warnings,
    }
