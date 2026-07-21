# Database Readiness

Use this before moving from JSON storage to PostgreSQL or Supabase.

## Local Default

The app stays on JSON storage unless PostgreSQL is explicitly enabled:

```bash
STORAGE_BACKEND=json
```

## PostgreSQL Mode

Set:

```bash
STORAGE_BACKEND=postgres
DATABASE_URL=postgresql://user:password@host:5432/database
DATABASE_CONNECT_TIMEOUT=10
```

`DATABASE_URL` is masked in readiness reports so secrets are not printed.

Production signaling polling uses the PostgreSQL `rate_limit_buckets` table for one atomic limit shared by every worker and application instance. Keys are SHA-256 hashes; participant email and call-room identifiers are never stored. Buckets expire automatically and are not part of JSON import/export because they are short-lived operational state.

## Readiness Check

Run:

```bash
python3 scripts/check_database_readiness.py --pretty
```

The report checks:

- Initial migration schema exists.
- Clean JSON data is ready for import.
- PostgreSQL configuration is valid.
- Import row counts are visible before staging import.

To see the full staging migration order in one report, run:

```bash
python3 scripts/staging_migration_plan.py --pretty
```

## Current Status

- Ready for staging import: true
- Storage backend: json
- PostgreSQL enabled: false
- Blockers: none
- Tests: 482 passed

## Next Step

Apply the ordered SQL files in `database/migrations/` to a staging PostgreSQL/Supabase database, then run the generated SQL from `database/import/generated_import.sql`. The schema application script discovers every `*.sql` migration in filename order, so existing databases receive incremental migrations such as `002_distributed_rate_limits.sql` without being recreated.

Before production deploy, also run:

```bash
python3 scripts/check_production_readiness.py --pretty
```

That check validates strong secrets, admin emails, production mode, PostgreSQL mode, verification providers, 2FA, and AI configuration.

For staging PostgreSQL/Supabase verification, set `STORAGE_BACKEND=postgres` and `DATABASE_URL`, then run:

```bash
python3 scripts/check_postgres_staging.py --pretty
```

That check verifies the database connection and confirms that every required table from `database/migrations/001_initial_schema.sql` exists.
It also validates critical columns and PostgreSQL data types, including the numeric feed post ID contract.

To apply the schema to staging, first dry-run:

```bash
python3 scripts/apply_postgres_schema.py --pretty
```

Then apply explicitly:

```bash
python3 scripts/apply_postgres_schema.py --apply --pretty
```

The apply script refuses to run unless PostgreSQL mode and `DATABASE_URL` are configured.

After generating `database/import/generated_import.sql`, dry-run the import:

```bash
python3 scripts/apply_postgres_import.py --pretty
```

Then apply explicitly:

```bash
python3 scripts/apply_postgres_import.py --apply --pretty
```

The import script also refuses to run unless PostgreSQL mode and `DATABASE_URL` are configured.

After applying the import, require exact row-count parity with the JSON import plan:

```bash
python3 scripts/check_postgres_staging.py --verify-data --pretty
```

This final check rejects partial imports even when every table exists.

## Repository Status

- Users: JSON and PostgreSQL repository implementations are available behind the existing storage functions.
- Messages: JSON and PostgreSQL repository implementations are available behind the existing storage functions.
- Social graph: JSON and PostgreSQL repository implementations are available behind the existing social functions.
- Social safety: JSON and PostgreSQL repository implementations are available for blocks, reports, restrictions, and hidden story authors.
- Moderation reports: report statuses, moderation metadata, and PostgreSQL export support are available.
- Admin moderation API: authenticated administrators can list, filter, summarize, and update report statuses.
- Admin moderation page: authenticated administrators can review and update reports through a CSRF-protected HTML page.
- Admin dashboard navigation: moderation tools are visible only to configured administrators.
- UI polish: dashboard navigation and settings use cleaner professional controls and tighter working-app styling.
- PostgreSQL staging verifier: `scripts/check_postgres_staging.py` checks connection and required tables before switching runtime storage.
- PostgreSQL schema apply: `scripts/apply_postgres_schema.py` provides dry-run by default and requires explicit `--apply`.
- PostgreSQL import apply: `scripts/apply_postgres_import.py` provides dry-run by default and requires explicit `--apply`.
- Call maintenance worker: `scripts/run_call_maintenance.py` is a bounded one-shot command for cron, systemd timers, or Kubernetes Jobs. It is dry-run by default; `--apply` expires due unanswered calls, records their call-history events, prunes stale rooms, and removes expired PostgreSQL limiter buckets. Reports contain aggregate counts only. PostgreSQL workers coordinate with `FOR UPDATE SKIP LOCKED`, so overlapping invocations do not process the same room.
- Production should schedule `python3 scripts/run_call_maintenance.py --apply` once per minute. Operators can first run `python3 scripts/run_call_maintenance.py --pretty` for a mutation-free report. The command exits after one batch and does not start a hidden thread inside Flask.
- Push delivery worker: `python3 scripts/run_push_delivery.py --pretty` performs a read-only readiness/count check; `python3 scripts/run_push_delivery.py --apply` claims at most 50 due jobs using `FOR UPDATE SKIP LOCKED`. Run apply mode every 5–10 seconds as a systemd timer or Kubernetes CronJob. It recovers abandoned 60-second locks, honors provider retry delays, caps attempts, expires stale calls, emits aggregate counts only, and requires PostgreSQL.
- Per-device delivery receipts are stored in `call_push_deliveries`, keyed by outbox event and device. Each device has independent attempts, next retry time, terminal status, and sanitized error code. A successful device is never resent merely because another device temporarily failed; the parent outbox job remains pending until no device retry is outstanding.
- FCM uses Application Default Credentials from `GOOGLE_APPLICATION_CREDENTIALS` plus `FCM_PROJECT_ID`. APNs uses a PushKit VoIP device token with `APNS_KEY_ID`, `APNS_TEAM_ID`, explicit `APNS_VOIP_TOPIC` (normally the app's VoIP topic), and `APNS_PRIVATE_KEY_FILE`; set `APNS_USE_SANDBOX=true` only outside production. Web Push uses `VAPID_PRIVATE_KEY_FILE` and a `VAPID_SUBJECT` such as `mailto:security@example.com`.
- Private keys must be mounted as read-only secret files and excluded from Git, container images, logs, database rows, and environment dumps. Provider modules load keys only inside the delivery worker and are lazy-imported, so the Flask process never needs to read delivery credentials.
- Staging migration plan: `scripts/staging_migration_plan.py` combines JSON readiness, schema dry-run, import dry-run, and staging database verification.
- Mobile token auth: API login and account verification return signed Bearer tokens, and `/api/me` accepts Bearer auth.
- I18n foundation: shared language detection and translation bundles now localize dashboard/settings from browser or device language headers.
- Auth i18n: login, registration, and onboarding screens now localize from browser or device language headers.
- Arabic UI support now includes RTL metadata for the first localized web/mobile startup screens.
- Feed: JSON and PostgreSQL repository implementations are available behind the existing feed functions.
- Notifications: JSON and PostgreSQL repository implementations are available behind the existing notification functions.
- Privacy settings: JSON and PostgreSQL repository implementations are available behind the existing privacy functions.
- Stories: JSON and PostgreSQL repository implementations are available behind the existing story storage functions.
- Proof items: JSON and PostgreSQL repository implementations are available behind the existing proof functions.
- AI memory: JSON and PostgreSQL repository implementations are available behind the existing AI memory functions.
- Security: JSON and PostgreSQL repository implementations are available for login attempts and audit events.
- Realtime: JSON and PostgreSQL repository implementations are available for typing and presence status.
- Calls: JSON and PostgreSQL repository implementations are available for call signals.
- News: JSON and PostgreSQL repository implementations are available behind the existing news functions.
- User AI settings: JSON and PostgreSQL repository implementations are available behind the existing user AI settings functions.
- Remaining local JSON mode should stay available as a fallback until staging database verification is complete.
