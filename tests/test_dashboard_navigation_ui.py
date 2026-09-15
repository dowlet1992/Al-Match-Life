from pathlib import Path


DASHBOARD = (
    Path(__file__).resolve().parents[1] / "frontend" / "dashboard.html"
).read_text(encoding="utf-8")
DASHBOARD_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "dashboard.css"
).read_text(encoding="utf-8")
DASHBOARD_JS = (
    Path(__file__).resolve().parents[1] / "static" / "dashboard.js"
).read_text(encoding="utf-8")
DASHBOARD_MEDIA = (
    Path(__file__).resolve().parents[1] / "frontend" / "dashboard_post_media.html"
).read_text(encoding="utf-8")
APP_SOURCE = (
    Path(__file__).resolve().parents[1] / "app.py"
).read_text(encoding="utf-8")
DASHBOARD_SOURCE = (
    Path(__file__).resolve().parents[1] / "backend" / "dashboard_routes.py"
).read_text(encoding="utf-8")


def test_logout_button_uses_the_same_full_width_navigation_geometry():
    assert ".menu a,\n.menu button{" in DASHBOARD_CSS
    assert "width:100%;" in DASHBOARD_CSS
    assert "min-height:44px;" in DASHBOARD_CSS
    assert "box-sizing:border-box;" in DASHBOARD_CSS
    assert ".menu form{" in DASHBOARD_CSS
    assert "font:inherit;" in DASHBOARD_CSS


def test_navigation_button_has_pointer_and_keyboard_feedback():
    assert ".menu a:hover,\n.menu button:hover{" in DASHBOARD_CSS
    assert ".menu a:focus-visible,\n.menu button:focus-visible{" in DASHBOARD_CSS
    assert ".logout:hover{" in DASHBOARD_CSS


def test_dashboard_behavior_and_styles_are_external():
    assert "<style" not in DASHBOARD
    assert "<script>" not in DASHBOARD
    assert " onclick=" not in DASHBOARD
    assert " onchange=" not in DASHBOARD
    assert "/static/dashboard.css" in DASHBOARD
    assert "/static/dashboard.js" in DASHBOARD
    assert "data-auto-submit" in DASHBOARD
    assert "requestSubmit()" in DASHBOARD_JS


def test_dashboard_media_markup_uses_a_template_component():
    dashboard_source = DASHBOARD_SOURCE

    assert 'render_template(' in dashboard_source
    assert '"dashboard_post_media.html"' in dashboard_source
    assert 'media_html += f"""' not in dashboard_source
    assert 'style="' not in DASHBOARD_MEDIA


def test_dashboard_does_not_build_posts_stories_or_admin_navigation_as_html_strings():
    dashboard_source = DASHBOARD_SOURCE

    assert "legacy_post_html" not in dashboard_source
    assert "stories_html" not in dashboard_source
    assert "admin_menu_html" not in dashboard_source
    assert "location_html" not in dashboard_source
    assert "hashtags_html" not in dashboard_source
