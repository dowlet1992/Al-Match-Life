# Database Migration Plan

The current app uses JSON files as local storage. That is acceptable for prototype work, but production and mobile need a real database.

## Recommended database

Use PostgreSQL first. Supabase is a strong option because it gives hosted Postgres, auth helpers, storage, and admin tooling.

## Initial tables

The first concrete schema draft is now tracked in `database/migrations/001_initial_schema.sql`.
The JSON-to-table mapping is tracked in `docs/JSON_TO_DATABASE_MAPPING.md`.

- `users`
  - account, profile, verification, trust fields.

- `privacy_settings`
  - one row per user.

- `social_follows`
  - follower and following relationships.

- `friend_requests`
  - sender, receiver, status.

- `friendships`
  - normalized user pair.

- `notifications`
  - target user, sender, type, text, read status.

- `messages`
  - sender, receiver, message, media, reactions, reply/forward metadata.

- `posts`
  - author, text, media, language, location, hashtags.

- `post_likes`, `post_comments`, `post_saves`, `post_shares`
  - feed interactions.

- `stories`
  - author, media, expiry.

- `proof_items`
  - proof profile records.

- `security_events`
  - security and audit logs.

## Migration order

1. Freeze JSON schema and export a backup.
2. Review and apply `database/migrations/001_initial_schema.sql`.
3. Run `python3 scripts/json_migration_inventory.py --pretty` to inspect JSON counts and missing user references.
4. Run `python3 scripts/build_json_import_plan.py --pretty` to confirm import order, row counts, and blockers.
5. Generate PostgreSQL import SQL with `python3 scripts/export_json_to_postgres_sql.py --pretty`.
6. Review `database/import/generated_import.sql` and `database/import/import_errors.json`.
7. Run `python3 scripts/check_database_readiness.py --pretty`.
8. Run the migration schema and generated SQL against a staging database first.
9. Add database-backed repository implementations behind the existing storage modules.
10. Move one module at a time: users, social, notifications, messages, feed.
11. Run web app and tests against database.
12. Keep JSON read-only fallback temporarily.
13. Remove JSON fallback after production verification.

Generated import files live under `database/import/` and are ignored by git because they can contain private user data.

## Do not migrate blindly

Before migration, clean test users, remove plaintext secrets, and decide which demo data should stay.
