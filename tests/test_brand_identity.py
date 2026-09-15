from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_primary_web_brand_is_novix_everywhere():
    templates = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "frontend").glob("*.html")
    )

    assert "NOVIX" in templates
    assert "AI Match Life" not in templates
    assert "Al Match Life" not in templates


def test_logo_and_favicon_use_the_novix_n_mark():
    logo = (ROOT / "static" / "app-logo.svg").read_text(encoding="utf-8")
    favicon = (ROOT / "static" / "favicon.svg").read_text(encoding="utf-8")

    for asset in (logo, favicon):
        assert "NOVIX" in asset
        assert "M15 47V17" in asset
        assert "41 35.2V17" in asset


def test_every_standalone_html_page_has_the_novix_brand_system():
    for path in (ROOT / "frontend").glob("*.html"):
        source = path.read_text(encoding="utf-8")
        if "<!doctype html" not in source.lower():
            continue
        assert (
            "app-logo.svg" in source
            or 'include "app_sidebar.html"' in source
            or 'include "brand_lockup.html"' in source
            or 'extends "base.html"' in source
        ), f"Standalone page has no NOVIX identity: {path.name}"


def test_public_base_and_error_pages_render_the_shared_brand_lockup():
    base = (ROOT / "frontend" / "base.html").read_text(encoding="utf-8")
    error = (ROOT / "frontend" / "error_page.html").read_text(encoding="utf-8")
    lockup = (ROOT / "frontend" / "brand_lockup.html").read_text(encoding="utf-8")

    assert 'include "brand_lockup.html"' in base
    assert 'include "brand_lockup.html"' in error
    assert "app-logo.svg" in lockup
    assert "NOVIX" in lockup


def test_unknown_web_page_uses_branded_novix_404():
    import app

    response = app.app.test_client().get("/definitely-not-a-novix-route")

    assert response.status_code == 404
    assert b"NOVIX" in response.data
    assert b"/static/app-logo.svg" in response.data
