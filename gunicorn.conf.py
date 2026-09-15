import multiprocessing
import os


def env_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
storage_backend = os.environ.get("STORAGE_BACKEND", "json").strip().lower()
requested_workers = env_int("WEB_CONCURRENCY", min(multiprocessing.cpu_count() * 2 + 1, 8), 1, 16)
# JSON repositories are safe for threads in one process but are not a
# production multi-process database. Scale worker processes only with Postgres.
workers = requested_workers if storage_backend == "postgres" else 1
worker_class = "gthread"
threads = env_int("GUNICORN_THREADS", 4, 1, 16)
timeout = env_int("GUNICORN_TIMEOUT", 60, 15, 300)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 30, 10, 120)
keepalive = env_int("GUNICORN_KEEPALIVE", 5, 1, 30)
max_requests = env_int("GUNICORN_MAX_REQUESTS", 2000, 100, 100000)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 200, 0, 10000)
preload_app = False
default_worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else "/tmp"
worker_tmp_dir = os.environ.get("GUNICORN_WORKER_TMP_DIR", default_worker_tmp_dir)
umask = 0o027
limit_request_line = env_int("GUNICORN_LIMIT_REQUEST_LINE", 4094, 1024, 8190)
limit_request_fields = env_int("GUNICORN_LIMIT_REQUEST_FIELDS", 100, 20, 200)
limit_request_field_size = env_int("GUNICORN_LIMIT_REQUEST_FIELD_SIZE", 8190, 1024, 16384)
accesslog = "-"
errorlog = "-"
capture_output = True
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
