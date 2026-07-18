from backend import security_store, verification_store
from backend.repositories import JsonStore
from backend.repositories.security_repository import JsonSecurityRepository


def test_login_attempts_store_accepts_only_dict(monkeypatch, tmp_path):
    repository = JsonSecurityRepository(tmp_path / "login_attempts.json", tmp_path / "security_log.json")
    repository.attempts_store.save([])
    monkeypatch.setattr(security_store, "get_security_repository", lambda: repository)

    assert security_store.load_login_attempts() == {}


def test_security_log_appends_and_limits_events(monkeypatch, tmp_path):
    repository = JsonSecurityRepository(tmp_path / "login_attempts.json", tmp_path / "security_log.json")
    monkeypatch.setattr(security_store, "get_security_repository", lambda: repository)

    security_store.append_security_event({"event": "one"}, limit=1)
    security_store.append_security_event({"event": "two"}, limit=1)

    assert security_store.load_security_events() == [{"event": "two"}]


def test_verification_codes_store_accepts_only_dict(monkeypatch, tmp_path):
    store = JsonStore(tmp_path / "verification_codes.json", {})
    store.save([])
    monkeypatch.setattr(verification_store, "_verification_codes_store", store)

    assert verification_store.load_verification_codes() == {}


def test_verification_codes_store_saves_codes(monkeypatch, tmp_path):
    store = JsonStore(tmp_path / "verification_codes.json", {})
    monkeypatch.setattr(verification_store, "_verification_codes_store", store)

    verification_store.save_verification_codes({"email:test@example.com": {"code": "123456"}})

    assert verification_store.load_verification_codes() == {
        "email:test@example.com": {"code": "123456"}
    }
