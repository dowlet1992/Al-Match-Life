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
- Tests after generation: 482 passed

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

Review the generated SQL locally, apply it to a staging PostgreSQL/Supabase database, then build database-backed repository implementations behind the current storage modules.
