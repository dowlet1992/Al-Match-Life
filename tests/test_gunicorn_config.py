import runpy
import os


def test_gunicorn_config_bounds_invalid_and_extreme_environment(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("WEB_CONCURRENCY", "999")
    monkeypatch.setenv("GUNICORN_THREADS", "invalid")
    monkeypatch.setenv("GUNICORN_TIMEOUT", "1")
    monkeypatch.setenv("GUNICORN_MAX_REQUESTS", "0")

    config = runpy.run_path("gunicorn.conf.py")

    assert config["workers"] == 16
    assert config["threads"] == 4
    assert config["timeout"] == 15
    assert config["max_requests"] == 100
    expected_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else "/tmp"
    assert config["worker_tmp_dir"] == expected_tmp_dir
    assert config["umask"] == 0o027
    assert config["limit_request_line"] == 4094


def test_gunicorn_uses_one_worker_for_json_storage(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "json")
    monkeypatch.setenv("WEB_CONCURRENCY", "8")

    config = runpy.run_path("gunicorn.conf.py")

    assert config["requested_workers"] == 8
    assert config["workers"] == 1


def test_gunicorn_allows_multiple_workers_with_postgres(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")

    config = runpy.run_path("gunicorn.conf.py")

    assert config["workers"] == 4


def test_gunicorn_launcher_uses_the_shared_config():
    source = open("scripts/run_web.sh", encoding="utf-8").read()

    assert "python3 -m gunicorn" in source
    assert "--config gunicorn.conf.py" in source
    assert "app:app" in source
