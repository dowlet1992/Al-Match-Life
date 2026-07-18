# PostgreSQL Import SQL Report

Generated with:

```bash
python3 scripts/export_json_to_postgres_sql.py --pretty
```

## Result

- Ready: true
- SQL output: `database/import/generated_import.sql`
- Error output: `database/import/import_errors.json`
- SQL statements: 291
- Import errors: 0
- Tests after generation: 83 passed

## Security Note

`database/import/` is ignored by git because generated SQL can contain private user data, email addresses, password hashes, messages, and audit logs.

## Next Step

Review the generated SQL locally, apply it to a staging PostgreSQL/Supabase database, then build database-backed repository implementations behind the current storage modules.
