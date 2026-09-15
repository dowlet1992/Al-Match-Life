import gzip
import re
from pathlib import Path

import app


def test_authenticated_user_opening_login_root_is_redirected_to_dashboard(monkeypatch):
    user = app.User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = "alice@example.com"
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard/alice@example.com"


def test_login_and_registration_pages_never_receive_authenticated_sidebar(monkeypatch):
    user = app.User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = "alice@example.com"

    register = client.get("/register")
    html = register.get_data(as_text=True)

    assert register.status_code == 200
    assert 'name="app-current-user"' not in html
    assert "app-shell-active" not in html


def test_guest_login_page_has_no_application_sidebar():
    response = app.app.test_client().get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="app-current-user"' not in html
    assert "app-shell-nav" not in html


def test_html_supports_gzip_and_etag():
    response = app.app.test_client().get("/", headers={"Accept-Encoding": "gzip"})

    assert response.headers["Content-Encoding"] == "gzip"
    assert response.headers.get("ETag")
    assert b"<html" in gzip.decompress(response.data).lower()


def test_private_html_etag_supports_zero_body_304():
    client = app.app.test_client()
    first = client.get("/")
    second = client.get("/", headers={"If-None-Match": first.headers["ETag"]})

    assert first.headers["Cache-Control"] == "private, no-cache"
    assert second.status_code == 304
    assert second.data == b""


def test_dashboard_no_longer_contains_logout_action(monkeypatch):
    source = open("frontend/dashboard.html", encoding="utf-8").read()
    settings = open("frontend/settings.html", encoding="utf-8").read()

    assert 'action="/logout"' not in source
    assert 'action="/logout"' in settings
    assert 'class="logout-button"' in settings


def test_settings_logout_uses_the_settings_design_system():
    stylesheet = Path("static/settings.css").read_text(encoding="utf-8")
    template = Path("frontend/settings.html").read_text(encoding="utf-8")

    assert ".logout-card{" in stylesheet
    assert ".logout-button{" in stylesheet
    assert ".logout-button:hover{" in stylesheet
    assert "danger-button" not in template


def test_shell_implements_ajax_navigation_with_server_fallback():
    source = open("static/app-shell.js", encoding="utf-8").read()

    assert "DOMParser" in source
    assert "fetch(url" in source
    assert "window.history.pushState" in source
    assert "window.history.replaceState" in source
    assert "window.addEventListener('popstate'" in source
    assert "X-Requested-With" in source
    assert "document.body.innerHTML" not in source
    assert "replacePageContent(nextDocument, sidebar)" in source
    assert "document.importNode" in source
    assert "app:navigation-before" in source


def test_follow_action_updates_profile_without_replacing_the_document():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")
    template = Path("frontend/profile_page.html").read_text(encoding="utf-8")

    assert "async function submitSocialFollow" in source
    assert "form.hasAttribute('data-social-follow')" in source
    assert "result.next_action" in source
    assert "[data-followers-stat] strong" in source
    assert "data-social-follow" in template
    assert "data-followers-stat" in template


def test_friend_request_actions_update_cards_without_page_reload():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")
    request_template = Path("frontend/social_list.html").read_text(encoding="utf-8")
    notification_template = Path("frontend/notifications.html").read_text(encoding="utf-8")

    assert "async function submitFriendRequest" in source
    assert "form.hasAttribute('data-friend-request-action')" in source
    assert "app:friend-request-changed" in source
    assert "data-remove-after-request" in request_template
    assert "data-friend-request-action" in request_template
    assert "data-friend-request-action" in notification_template


def test_feed_mutations_update_one_post_without_page_reload():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")
    template = Path("frontend/dashboard_post_card.html").read_text(encoding="utf-8")

    assert "async function submitFeedMutation" in source
    assert "form.hasAttribute('data-feed-mutation')" in source
    assert "app:feed-changed" in source
    assert "data-feed-post" in template
    assert 'data-feed-mutation="like"' in template
    assert 'data-feed-mutation="save"' in template
    assert 'data-feed-mutation="comment"' in template
    assert 'data-feed-mutation="report"' in template
    assert 'data-feed-mutation="delete"' in template


def test_shell_back_navigation_stays_inside_the_application():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")

    assert "historyMarker = 'novix'" in source
    assert "Number(currentState.depth) > 0" in source
    assert "navigate(dashboardUrl(), {}, 'replace')" in source
    assert "window.history.length > 1" not in source
    assert "initializeBackControl()" in source
    assert "className = 'app-shell-back'" in source


def test_explicit_page_back_links_use_the_shared_history_controller():
    for template_name in (
        "author_info.html", "post_detail.html", "post_translation.html",
        "settings.html", "share_post.html",
    ):
        source = Path("frontend", template_name).read_text(encoding="utf-8")
        assert "data-back" in source, template_name


def test_shell_commits_the_final_redirect_url():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")

    assert "const finalUrl = response.url || url" in source
    assert "applyDocument(await response.text(), finalUrl, historyMode)" in source


def test_navigation_uses_latest_click_instead_of_silently_ignoring_it():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")
    navigation = source[source.index("async function navigate"):source.index("async function submitSocialFollow")]

    assert "state.navigationController?.abort()" in navigation
    assert "signal: controller.signal" in navigation
    assert "if (state.busy) return" not in navigation


def test_sidebar_ai_assistant_targets_authenticated_account():
    source = Path("frontend/app_sidebar.html").read_text(encoding="utf-8")
    assert 'href="/ai_copilot/{{ shell_account_target }}"' in source


def test_shell_removes_legacy_dashboard_offset_and_centers_content():
    stylesheet = Path("static/app-shell.css").read_text(encoding="utf-8")

    assert "body.app-shell-active > .layout .main" in stylesheet
    assert "margin: 0 auto" in stylesheet
    assert "max-width: 1320px" in stylesheet


def test_authenticated_shell_is_rendered_on_the_server_with_complete_navigation(monkeypatch):
    user = app.User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [user])
    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = user.email

    response = client.get(f"/messages/{user.email}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count('class="app-shell-nav"') == 1
    assert f'href="/profile/{user.id}"' in html
    assert f'href="/ai_copilot/{user.id}"' in html
    assert f'href="/notifications/{user.id}"' in html
    assert f'href="/search/{user.id}"' in html
    assert f'href="/messages/{user.id}" aria-current="page"' in html


def test_shell_javascript_does_not_generate_a_second_sidebar():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")

    assert "document.createElement('aside')" not in source
    assert "document.body.prepend(nav)" not in source
    assert "document.querySelector('.app-shell-nav')" in source
    assert "const translations =" not in source


def test_shell_dynamic_copy_uses_the_same_server_language_as_the_page(monkeypatch):
    user = app.User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    user.language = "tr"
    monkeypatch.setattr(app, "users", [user])
    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = user.email

    response = client.get(f"/messages/{user.email}", headers={"Accept-Language": "en-US"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<html lang="tr" dir="ltr">' in html
    assert 'data-copy-failed="İşlem tamamlanamadı"' in html
    assert 'data-copy-join="Katıl"' in html
    assert 'data-copy-decline="Reddet"' in html
    assert 'data-copy-invites="sizi bir aramaya davet ediyor"' in html


def test_shell_preserves_sidebar_and_manages_page_specific_head_assets():
    source = Path("static/app-shell.js").read_text(encoding="utf-8")

    assert "function syncSidebar(nextDocument)" in source
    assert "currentSidebar.replaceChildren(" in source
    assert "function markInitialDynamicHead()" in source
    assert "function activateHeadScripts(nextDocument)" in source
    assert "script.async = false" in source


def test_standalone_authenticated_templates_include_the_shared_sidebar():
    for template_name in ("chat.html", "dashboard.html", "profile.html", "settings.html"):
        source = Path("frontend", template_name).read_text(encoding="utf-8")
        assert '{% include "app_sidebar.html" %}' in source
        assert 'class="app-shell-active"' in source


def test_every_full_authenticated_page_uses_the_shared_shell():
    allowed_without_sidebar = {
            "app_sidebar.html", "brand_lockup.html", "call.html", "conference.html", "dashboard_post_card.html",
        "dashboard_post_media.html", "dashboard_posts_empty.html", "error_page.html",
        "index.html", "register.html",
    }
    for template in Path("frontend").glob("*.html"):
        source = template.read_text(encoding="utf-8")
        if template.name in allowed_without_sidebar:
            continue
        assert '{% extends "base.html" %}' in source or '{% include "app_sidebar.html" %}' in source, template.name


def test_shell_brand_and_accessibility_text_follow_saved_language(monkeypatch):
    user = app.User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    user.language = "de"
    monkeypatch.setattr(app, "users", [user])
    client = app.app.test_client()
    with client.session_transaction() as session_data:
        session_data["user_email"] = user.email

    response = client.get(f"/messages/{user.email}", headers={"Accept-Language": "ru-RU"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Menschen intelligent verbinden" in html
    assert 'aria-label="Anwendungsnavigation"' in html
    assert "Умные связи между людьми" not in html
    assert "Human connection, intelligently" not in html


def test_mobile_shell_keeps_settings_in_the_five_item_navigation():
    stylesheet = Path("static/app-shell.css").read_text(encoding="utf-8")
    mobile = stylesheet[stylesheet.index("@media (max-width: 820px)"):]

    assert "grid-template-columns: repeat(5" in mobile
    assert ".app-shell-footer { display: contents; }" in mobile
    assert ".app-shell-footer a:not(:last-child)" in mobile
    assert ".app-shell-links a:nth-child(2)" in mobile
    assert ".app-shell-links a:nth-child(8)" in mobile


def test_sidebar_renders_accessible_unread_notification_badge():
    template = Path("frontend/app_sidebar.html").read_text(encoding="utf-8")
    stylesheet = Path("static/app-shell.css").read_text(encoding="utf-8")

    assert "shell_unread_notifications" in template
    assert 'class="app-shell-badge"' in template
    assert 'aria-label="{{ shell_unread_notifications }}"' in template
    assert ".app-shell-badge" in stylesheet


def test_public_social_links_use_stable_user_uuid():
    profile = Path("frontend/profile_page.html").read_text(encoding="utf-8")
    dashboard = Path("frontend/dashboard.html").read_text(encoding="utf-8")

    assert 'href="/followers/{{ user.id }}"' in profile
    assert 'href="/following/{{ user.id }}"' in profile
    assert 'href="/followers/{{ user_id }}"' in dashboard
    assert 'href="/following/{{ user_id }}"' in dashboard


def test_python_routes_do_not_reinterpret_template_files():
    source = Path("app.py").read_text(encoding="utf-8")
    dashboard_routes = Path("backend/dashboard_routes.py").read_text(encoding="utf-8")
    account_routes = Path("backend/account_page_routes.py").read_text(encoding="utf-8")

    assert "render_template_string" not in source
    assert '"dashboard.html",' in dashboard_routes
    assert '"settings.html",' in account_routes


def test_error_pages_use_external_styles_and_links():
    source = Path("frontend/error_page.html").read_text(encoding="utf-8")

    assert "/static/error-page.css" in source
    assert "<style" not in source
    assert " onclick=" not in source


def test_python_does_not_embed_executable_frontend_code():
    sources = [
        Path("app.py").read_text(encoding="utf-8"),
        *(
            path.read_text(encoding="utf-8")
            for path in Path("backend").rglob("*.py")
        ),
    ]
    combined = "\n".join(sources)

    assert "<style>" not in combined
    assert "<script>" not in combined
    for event_name in (" onclick=", " onchange=", " oninput=", " onload=", " onsubmit="):
        assert event_name not in combined


def test_security_middleware_does_not_rewrite_rendered_html():
    source = Path("app.py").read_text(encoding="utf-8")
    middleware = source[
        source.index("def add_security_headers(response):"):
        source.index("def allowed_file(filename):")
    ]

    assert "response.get_data(as_text=True)" not in middleware
    assert "response.set_data(html)" not in middleware
    assert "re.sub(" not in middleware
    assert "shell_head" not in middleware
