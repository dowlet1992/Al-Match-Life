import importlib
import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_STORAGE_BACKEND = "json"
SUPPORTED_STORAGE_BACKENDS = {"json", "postgres"}


@dataclass(frozen=True)
class DatabaseSettings:
    storage_backend: str = DEFAULT_STORAGE_BACKEND
    database_url: str = ""
    connect_timeout_seconds: int = 10

    @property
    def postgres_enabled(self):
        return self.storage_backend == "postgres"

    @property
    def ready_for_postgres(self):
        return self.postgres_enabled and bool(self.database_url)


def load_database_settings(environ=None):
    environ = environ or os.environ
    storage_backend = str(environ.get("STORAGE_BACKEND", DEFAULT_STORAGE_BACKEND)).strip().lower()
    if storage_backend not in SUPPORTED_STORAGE_BACKENDS:
        storage_backend = DEFAULT_STORAGE_BACKEND

    try:
        connect_timeout_seconds = int(environ.get("DATABASE_CONNECT_TIMEOUT", "10"))
    except ValueError:
        connect_timeout_seconds = 10

    return DatabaseSettings(
        storage_backend=storage_backend,
        database_url=str(environ.get("DATABASE_URL", "")).strip(),
        connect_timeout_seconds=max(connect_timeout_seconds, 1),
    )


def mask_database_url(database_url):
    if not database_url:
        return ""

    parts = urlsplit(database_url)
    netloc = parts.netloc

    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        if ":" in credentials:
            username, _password = credentials.split(":", 1)
            netloc = f"{username}:***@{host}"
        else:
            netloc = f"***@{host}"

    query_items = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if "password" in key.lower() or "token" in key.lower() or "secret" in key.lower():
            query_items.append((key, "***"))
        else:
            query_items.append((key, value))

    return urlunsplit((
        parts.scheme,
        netloc,
        parts.path,
        urlencode(query_items),
        parts.fragment,
    ))


def validate_database_settings(settings):
    issues = []

    if settings.storage_backend not in SUPPORTED_STORAGE_BACKENDS:
        issues.append("Unsupported storage backend.")

    if settings.postgres_enabled and not settings.database_url:
        issues.append("DATABASE_URL is required when STORAGE_BACKEND=postgres.")

    if settings.database_url and not settings.database_url.startswith(("postgresql://", "postgres://")):
        issues.append("DATABASE_URL must start with postgresql:// or postgres://.")

    return issues


class PostgresClient:
    def __init__(self, settings=None):
        self.settings = settings or load_database_settings()

    def connect(self):
        issues = validate_database_settings(self.settings)
        if issues:
            raise RuntimeError("; ".join(issues))

        try:
            psycopg = importlib.import_module("psycopg")
        except ImportError as error:
            raise RuntimeError("PostgreSQL support requires installing psycopg[binary].") from error

        return psycopg.connect(
            self.settings.database_url,
            connect_timeout=self.settings.connect_timeout_seconds,
        )
