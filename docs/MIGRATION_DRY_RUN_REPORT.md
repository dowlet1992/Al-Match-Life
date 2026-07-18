# Migration Dry Run Report

Generated with:

```bash
python3 scripts/json_migration_inventory.py --pretty
```

## Current Counts After Cleanup

- Users: 8
- Messages: 24
- Social follows: 0
- Friendships: 1
- Friend requests: 0
- Feed posts: 6
- Notifications: 8
- Stories: 1
- Proof items: 0
- Reports: 0

## Current Data Issues After Cleanup

- Missing user references: 0
- Repeated missing email: none

## Cleanup Applied

- Removed orphan references to `testweb@test.com` from messages, social requests, feed posts/interactions, notifications, and stories.
- Backups were created under `backups/orphan_cleanup_*`.

## Migration Decision Needed

- Keep the backup folders until the database import is verified.
- Continue using `python3 scripts/json_migration_inventory.py --pretty` before each migration attempt.
