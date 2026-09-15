import app
from backend.models import User


def test_profile_blocked_state_escapes_name_and_contains_csrf(monkeypatch):
    alice = User("Alice", 28, "alice@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    bob = User("<script>alert(1)</script>", 30, "bob@example.com", "hashed", "Germany", "", "", "", [], [], [], [])
    monkeypatch.setattr(app, "users", [alice, bob])
    monkeypatch.setattr(app, "normalize_user_ai_settings", lambda email: {"profile_visibility": "public"})
    monkeypatch.setattr(app, "is_blocked", lambda blocker, blocked: blocker == alice.email and blocked == bob.email)
    monkeypatch.setattr(app, "are_friends", lambda one, two: False)
    monkeypatch.setattr(app, "get_avatar_url", lambda email: f"/avatar/{email}.png")
    client = app.app.test_client()
    with client.session_transaction() as session:
        session["user_email"] = alice.email
        session["csrf_token"] = "blocked-csrf"

    response = client.get(f"/profile/{bob.email}")

    assert response.status_code == 200
    assert b"<script>alert(1)</script>" not in response.data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in response.data
    assert b"/unblock_user/alice@example.com/bob@example.com" in response.data
    assert b'value="blocked-csrf"' in response.data
