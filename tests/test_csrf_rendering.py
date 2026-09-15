from markupsafe import Markup

from backend.csrf import render_csrf_input


def test_csrf_input_is_trusted_markup_with_escaped_token():
    field = render_csrf_input('token" onfocus="alert(1)')

    assert isinstance(field, Markup)
    assert 'value="token&#34; onfocus=&#34;alert(1)"' in str(field)
    assert 'value="token" onfocus=' not in str(field)


def test_app_delegates_csrf_markup_outside_main_module():
    source = open("app.py", encoding="utf-8").read()
    csrf_source = source[source.index("def csrf_input():"):source.index("# --- Multilanguage helpers ---")]

    assert "render_csrf_input(get_csrf_token())" in csrf_source
    assert "<input" not in csrf_source
