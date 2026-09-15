# PostgreSQL Import SQL Report

Generated with:

```bash
python3 scripts/export_json_to_postgres_sql.py --pretty
```

## Result

- Ready: true
- SQL output: `database/import/generated_import.sql`
- Error output: `database/import/import_errors.json`
- SQL statements: 1099
- Import errors: 0
- Full tests after cleanup and configuration hardening: 992 passed
- Staging import: applied successfully on 2026-09-06
- Staging verification: 32 required tables, exact row-count parity, 0 blockers
- Production release gate: ready, all 5 local gates passed

Feed post identifiers remain positive integers in PostgreSQL so migrated posts keep
the same IDs used by the web routes and API contract. Export now fails closed: if
any source row is invalid, no import SQL is marked ready or written for application.

The exporter now covers every dataset in the import plan, including privacy and AI
settings, relationship safety controls, proofs, verification and login security,
news, realtime presence/typing, and call signaling state. Verification codes are
hashed during export and plaintext codes are never written into generated SQL.

## Security Note

`database/import/` is ignored by git because generated SQL can contain private user data, email addresses, password hashes, messages, and audit logs.

## Next Step

Keep the verified pre-import and post-import dumps plus backup-set manifest. Before
external production cutover, configure production LiveKit credentials, Android FCM,
iOS APNs, the public domain/TLS environment, and signed mobile build toolchains.
Database-backed repositories are already present behind the storage modules.
