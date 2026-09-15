# Migration Dry Run Report

Generated with:

```bash
python3 scripts/json_migration_inventory.py --pretty
```

## Current Counts After Cleanup

- Users: 8
- Messages: 0
- Social follows: 1
- Friendships: 1
- Friend requests: 0
- Feed posts: 6
- Notifications: 18
- Stories: 1
- Proof items: 0
- Reports: 0

## Current Data Issues After Cleanup

- Missing user references: 0
- Repeated missing email: none

## Cleanup Applied

- On 2026-09-06, removed five orphan message rows referencing absent legacy test
  accounts. No social, feed, notification, story, or AI rows required changes.
- The source file backup is stored under
  `backups/orphan_cleanup_20260906_200350/` and has been SHA-256 verified.
- A second verified cleanup backup is stored under
  `backups/orphan_cleanup_20260906_201106/` after test-state isolation was fixed.
- The full test suite now leaves `messages.json` unchanged (992 tests passed;
  identical SHA-256 before and after the run).

## Migration Status

- The staging import and exact row-count verification passed for all 32 tables.
- Keep the cleanup and database backup folders through the production cutover.
- Continue using `python3 scripts/json_migration_inventory.py --pretty` before each migration attempt.
