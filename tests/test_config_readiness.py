from backend.config import (
    build_production_readiness_report,
    has_email_provider,
    has_secure_secret_key,
    has_sms_provider,
    has_turn_provider,
    is_admin_email,
    is_production_environment,
    parse_admin_emails,
)


def test_is_production_environment_accepts_flask_or_app_env():
    assert is_production_environment({"FLASK_ENV": "production"}) is True
    assert is_production_environment({"APP_ENV": "production"}) is True
    assert is_production_environment({"FLASK_ENV": "development"}) is False


def test_secure_secret_key_rejects_placeholders():
    assert has_secure_secret_key({"FLASK_SECRET_KEY": "change-me"}) is False
    assert has_secure_secret_key({"FLASK_SECRET_KEY": "x" * 32}) is True


def test_admin_email_parser_supports_commas_and_semicolons():
    emails = parse_admin_emails("Admin@Example.com; owner@example.com, ")

    assert emails == {"admin@example.com", "owner@example.com"}
    assert is_admin_email("ADMIN@example.com", {"ADMIN_EMAILS": "admin@example.com"}) is True
    assert is_admin_email("user@example.com", {"ADMIN_EMAILS": "admin@example.com"}) is False


def test_provider_checks_require_complete_credentials():
    assert has_email_provider({
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USER": "user",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM": "noreply@example.com",
    }) is True
    assert has_email_provider({"SMTP_HOST": "smtp.example.com"}) is False

    assert has_sms_provider({
        "TWILIO_ACCOUNT_SID": "sid",
        "TWILIO_AUTH_TOKEN": "token",
        "TWILIO_VERIFY_SERVICE_SID": "service",
    }) is True
    assert has_sms_provider({"TWILIO_ACCOUNT_SID": "sid"}) is False
    assert has_turn_provider({"TWILIO_ACCOUNT_SID": "sid", "TWILIO_AUTH_TOKEN": "token"}) is True
    assert has_turn_provider({"TWILIO_ACCOUNT_SID": "sid"}) is False


def test_production_readiness_blocks_unsafe_production_config():
    report = build_production_readiness_report({
        "FLASK_ENV": "production",
        "FLASK_SECRET_KEY": "change-me",
        "STORAGE_BACKEND": "json",
    })

    assert report["ready_for_production"] is False
    assert "FLASK_SECRET_KEY must be a strong unique value in production." in report["blockers"]
    assert "ADMIN_EMAILS must include at least one administrator in production." in report["blockers"]
    assert "STORAGE_BACKEND should be postgres in production." in report["blockers"]
    assert "Configure SMTP or Twilio before production account verification." in report["blockers"]
    assert "Configure Twilio Network Traversal credentials for reliable production calls." in report["blockers"]
    assert "Configure at least one FCM, APNs, or Web Push provider for production call delivery." in report["blockers"]


def test_production_readiness_passes_strong_config_and_masks_database_url():
    report = build_production_readiness_report({
        "FLASK_ENV": "production",
        "FLASK_SECRET_KEY": "x" * 40,
        "ADMIN_EMAILS": "admin@example.com",
        "STORAGE_BACKEND": "postgres",
        "DATABASE_URL": "postgresql://user:secret@example.com/db",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USER": "user",
        "SMTP_PASSWORD": "smtp-secret",
        "SMTP_FROM": "noreply@example.com",
        "LOGIN_2FA_ENABLED": "true",
        "OPENAI_API_KEY": "sk-test",
        "TWILIO_ACCOUNT_SID": "AC-test",
        "TWILIO_AUTH_TOKEN": "twilio-secret",
        "GOOGLE_APPLICATION_CREDENTIALS": "/run/secrets/google-service-account.json",
        "FCM_PROJECT_ID": "ai-match-life",
    })

    assert report["ready_for_production"] is True
    assert report["blockers"] == []
    assert "secret" not in report["database_url"]
    assert report["checks"]["openai_configured"] is True
    assert report["checks"]["push_providers"]["android"] is True
