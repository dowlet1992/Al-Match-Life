# NOVIX production deployment

The production stack runs a non-root Gunicorn application, PostgreSQL 16,
Ollama, and a private nginx origin. Uploaded photos, videos, documents, and
voice messages persist in the host directory configured by `NOVIX_MEDIA_DIR`
across web-container replacement. Port 8080 binds only to localhost and must
sit behind an HTTPS edge proxy or tunnel that overwrites forwarded headers.

1. Copy `.env.example` to a secret environment file outside Git and fill every
   variable required by `deploy/docker-compose.production.yml`.
   Generate `runtime-secrets/flask-secret` with at least 32 random bytes and a
   VAPID key pair in `runtime-secrets/vapid-private.pem`; this directory is
   excluded from Git and mounted read-only through Docker secrets.
2. Create the media directory with ownership matching container user `novix`,
   and set its absolute path in `NOVIX_MEDIA_DIR`. Keep it outside Git.
3. Start PostgreSQL only, apply every migration, generate the JSON import SQL,
   import it, and require exact row-count parity before starting the web app.
   The import is required only for the initial JSON-to-PostgreSQL cutover.
4. Start the complete stack and verify `/api/health` and `/api/readiness`.
5. Run the release gate, security checks, and one restore drill before opening
   public traffic.

Never expose PostgreSQL, Ollama, or Gunicorn directly.

`/api/health` is a dependency-free liveness probe. `/api/readiness` verifies an
actual PostgreSQL query plus configured AI and speech providers and returns
HTTP 503 while any required component is unavailable. Every response carries
an `X-Request-ID`; stdout receives one compact JSON request record containing
only method, path without query parameters, status, duration, and request ID.
Forward these container logs to the selected monitoring service and alert on
readiness failures and sustained 5xx responses.

## Initial database cutover

Run from the repository root. Replace the example environment-file path with
the protected production file. Keep `database/import/generated_import.sql`
private; it is intentionally excluded from images and Git.

```sh
export NOVIX_ENV_FILE=/etc/novix/novix.env
docker compose --env-file "$NOVIX_ENV_FILE" -f deploy/docker-compose.production.yml up -d postgres
docker compose --env-file "$NOVIX_ENV_FILE" -f deploy/docker-compose.production.yml run --rm --no-deps web python scripts/apply_postgres_schema.py --apply --pretty
docker compose --env-file "$NOVIX_ENV_FILE" -f deploy/docker-compose.production.yml exec -T postgres psql -v ON_ERROR_STOP=1 -U novix -d novix < database/import/generated_import.sql
docker compose --env-file "$NOVIX_ENV_FILE" -f deploy/docker-compose.production.yml run --rm --no-deps web python scripts/check_postgres_staging.py --verify-data --pretty
```

Do not repeat the initial import against a populated production database. Later
deployments apply only ordered migrations before starting the updated web image.

The repository intentionally does not auto-import JSON on container startup:
an automatic destructive import is unsafe and can duplicate or overwrite
production data.

The proxy waits for the web health check before accepting traffic. Web uses an
init process and a 45-second stop grace period so Gunicorn can finish in-flight
requests before Docker terminates the container. Its root filesystem is
read-only, Linux capabilities are dropped, privilege escalation is disabled,
and only `/tmp` plus the dedicated media volume are writable. Include both the PostgreSQL
volume and `NOVIX_MEDIA_DIR` in the external encrypted backup policy; database-only
backups do not protect uploaded media.

Create and validate the media archive before release:

```sh
python3 scripts/backup_media.py --source uploads --pretty
python3 scripts/check_media_backup_health.py --pretty
```

The production scheduler should run the same commands against
`NOVIX_MEDIA_DIR`. A stale or invalid media archive blocks the release gate.
For the normal daily operation use `scripts/run_full_backup_job.py`, which
publishes one verified set manifest only after both PostgreSQL and media
backups succeed.

```sh
python3 scripts/run_full_backup_job.py \
  --container novix-postgres-production \
  --database novix \
  --user novix \
  --media-source /var/lib/novix/uploads \
  --backup-root /var/backups/novix \
  --encrypt-for-offsite \
  --pretty
```

Schedule `scripts/run_call_maintenance.py --apply` once per minute and
`scripts/run_push_delivery.py --apply` every 5–10 seconds using systemd,
Kubernetes, or another supervised scheduler. These are bounded one-shot jobs;
failure must be reported by the scheduler instead of hidden inside Gunicorn.

## Public HTTPS

After DNS for `NOVIX_DOMAIN` points to the server and a Let's Encrypt
certificate exists, enable the TLS override:

```sh
docker compose --env-file /secure/path/novix.env \
  -f deploy/docker-compose.production.yml \
  -f deploy/docker-compose.tls.yml up -d
```

The TLS proxy redirects HTTP to HTTPS, supports WebSocket upgrades, sends HSTS,
and keeps PostgreSQL, Ollama, and Gunicorn off the public network. Certificate
issuance is intentionally external because it requires control of the real
domain and its DNS records.
