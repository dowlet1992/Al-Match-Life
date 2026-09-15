import re

import app
import pytest


def test_security_headers_and_csp_do_not_allow_inline_scripts():
    response = app.app.test_client().get("/api/health")

    assert response.headers["Cross-Origin-Embedder-Policy"] == "require-corp"
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    csp = response.headers["Content-Security-Policy"]
    script_src = re.search(r"(?:^|;\s*)script-src\s+([^;]+)", csp).group(1)
    image_src = re.search(r"(?:^|;\s*)img-src\s+([^;]+)", csp).group(1)
    media_src = re.search(r"(?:^|;\s*)media-src\s+([^;]+)", csp).group(1)
    assert "'unsafe-inline'" not in script_src
    assert script_src.strip() == "'self'"
    assert "data:" not in image_src
    assert "data:" not in media_src


def test_html_uses_only_external_scripts_without_inline_event_handlers():
    response = app.app.test_client().get("/")
    csp = response.headers["Content-Security-Policy"]
    html = response.get_data(as_text=True)

    assert "<script" in html
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html, re.IGNORECASE)
    assert not re.search(r"\son[a-z]+\s*=", html, re.IGNORECASE)
    assert 'script-src-attr \'none\'' in csp
    assert "'unsafe-hashes'" not in csp


def test_options_does_not_disclose_route_methods_or_enable_cors():
    client = app.app.test_client()
    response = client.options("/api/health")

    assert response.status_code == 204
    assert "Allow" not in response.headers
    assert "Access-Control-Allow-Origin" not in response.headers

    rejected = client.options("/api/health", headers={"Origin": "https://evil.example"})
    assert rejected.status_code == 403
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_production_cookie_and_hsts(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    original_secure = app.app.config["SESSION_COOKIE_SECURE"]
    app.app.config["SESSION_COOKIE_SECURE"] = True
    try:
        client = app.app.test_client()
        response = client.get("/", base_url="https://example.test")
    finally:
        app.app.config["SESSION_COOKIE_SECURE"] = original_secure

    assert "Secure" in response.headers.getlist("Set-Cookie")[0]
    assert "SameSite=Strict" in response.headers.getlist("Set-Cookie")[0]
    assert response.headers["Strict-Transport-Security"].startswith("max-age=31536000")


def test_production_requires_a_strong_explicit_session_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    monkeypatch.delenv("FLASK_SECRET_KEY_FILE", raising=False)
    with pytest.raises(RuntimeError, match="required in production"):
        app.get_app_secret_key()

    monkeypatch.setenv("FLASK_SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        app.get_app_secret_key()
