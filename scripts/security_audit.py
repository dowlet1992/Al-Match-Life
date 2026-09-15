import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check(name, passed, detail=""):
    return {"name": name, "passed": bool(passed), "detail": detail}


def build_security_audit(application_module=None, root=None):
    if application_module is None:
        import app as application_module
    root_path = Path(root or PROJECT_ROOT)
    application = application_module
    client = application.app.test_client()
    root = client.get("/")
    source = (root_path / "app.py").read_text(encoding="utf-8")
    search_source = (root_path / "backend/search.py").read_text(encoding="utf-8")
    checks = [
        check("content_security_policy", bool(root.headers.get("Content-Security-Policy"))),
        check("clickjacking_protection", root.headers.get("X-Frame-Options") in {"DENY", "SAMEORIGIN"}),
        check("mime_sniffing_protection", root.headers.get("X-Content-Type-Options") == "nosniff"),
        check("referrer_policy", bool(root.headers.get("Referrer-Policy"))),
        check("permissions_policy", bool(root.headers.get("Permissions-Policy"))),
        check("private_html_cache", "private" in root.headers.get("Cache-Control", "")),
        check("no_embedded_templates", "render_template_string" not in source),
        check("no_plaintext_password_fallback", "stored_password == raw_password" not in source),
        check("legacy_search_rejects_plaintext", "user.password == password" not in search_source),
        check("debug_disabled", not application.app.debug),
    ]
    return {"ok": all(item["passed"] for item in checks), "checks": checks}


def main():
    payload = build_security_audit()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
