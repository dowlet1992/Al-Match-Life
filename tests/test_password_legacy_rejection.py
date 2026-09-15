from types import SimpleNamespace

from backend.search import find_user_by_email_and_password


def test_legacy_plaintext_password_is_never_accepted():
    user = SimpleNamespace(email="user@example.com", password="plaintext-secret")
    assert find_user_by_email_and_password([user], user.email, "plaintext-secret") is None


def test_runtime_password_verifier_has_no_plaintext_fallback():
    source = open("app.py", encoding="utf-8").read()
    verifier = source[source.index("def verify_user_password"):source.index("def login_required")]
    assert "stored_password == raw_password" not in verifier
