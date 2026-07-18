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
- Tests: 284 passed

## Next Step

Apply `database/migrations/001_initial_schema.sql` to a staging PostgreSQL/Supabase database, then run the generated SQL from `database/import/generated_import.sql`.

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
