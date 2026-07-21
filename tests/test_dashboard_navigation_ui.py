from pathlib import Path


DASHBOARD = (
    Path(__file__).resolve().parents[1] / "frontend" / "dashboard.html"
).read_text(encoding="utf-8")


def test_logout_button_uses_the_same_full_width_navigation_geometry():
    assert ".menu a,\n.menu button{" in DASHBOARD
    assert "width:100%;" in DASHBOARD
    assert "min-height:44px;" in DASHBOARD
    assert "box-sizing:border-box;" in DASHBOARD
    assert ".menu form{" in DASHBOARD
    assert "font:inherit;" in DASHBOARD


def test_navigation_button_has_pointer_and_keyboard_feedback():
    assert ".menu a:hover,\n.menu button:hover{" in DASHBOARD
    assert ".menu a:focus-visible,\n.menu button:focus-visible{" in DASHBOARD
    assert ".logout:hover{" in DASHBOARD
