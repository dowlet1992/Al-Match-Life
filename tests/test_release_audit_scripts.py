from pathlib import Path


def test_release_audits_are_read_only_and_bounded():
    load = Path("scripts/load_smoke.py").read_text(encoding="utf-8")
    security = Path("scripts/security_audit.py").read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" in load
    assert "--requests" in load and "--concurrency" in load
    assert "client.get(path)" in load
    assert "client.post(" not in load
    assert "Content-Security-Policy" in security
    assert "no_plaintext_password_fallback" in security
