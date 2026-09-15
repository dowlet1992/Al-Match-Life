from pathlib import Path

import yaml


def production_compose():
    return yaml.safe_load(Path("deploy/docker-compose.production.yml").read_text(encoding="utf-8"))


def test_production_web_persists_uploaded_media():
    compose = production_compose()
    web = compose["services"]["web"]

    assert web["environment"]["MEDIA_UPLOAD_FOLDER"] == "/app/uploads"
    assert any(
        item.startswith("${NOVIX_MEDIA_DIR:?") and item.endswith(":/app/uploads")
        for item in web["volumes"]
    )
    assert "novix-media" not in compose["volumes"]


def test_production_postgres_has_stable_backup_target():
    postgres = production_compose()["services"]["postgres"]

    assert postgres["container_name"] == "novix-postgres-production"


def test_production_proxy_waits_for_healthy_graceful_web_process():
    web = production_compose()["services"]["web"]
    proxy = production_compose()["services"]["proxy"]

    assert web["init"] is True
    assert web["stop_grace_period"] == "45s"
    assert "/api/health" in " ".join(web["healthcheck"]["test"])
    assert proxy["depends_on"]["web"]["condition"] == "service_healthy"


def test_production_web_runs_with_least_privilege_and_writable_scoped_mounts():
    web = production_compose()["services"]["web"]
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert web["read_only"] is True
    assert "no-new-privileges:true" in web["security_opt"]
    assert web["cap_drop"] == ["ALL"]
    assert any(item.startswith("/tmp:rw,noexec,nosuid") for item in web["tmpfs"])
    assert "USER novix" in dockerfile
    assert "chown novix:novix /app/uploads" in dockerfile
