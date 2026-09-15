# JSON Import Plan Report

Generated with:

```bash
python3 scripts/build_json_import_plan.py --pretty
```

## Status

- Ready: true
- Blockers: none
- Warnings: none

## Planned Row Counts

- Users: 8
- Auth refresh sessions: 0
- User AI settings: 1
- Privacy settings: 8
- Social follows: 1
- Friendships: 1
- Friend requests: 0
- User blocks: 0
- User restrictions: 0
- Hidden story authors: 0
- Notifications: 18
- Messages: 0
- Feed posts: 6
- Feed post likes: 4
- Feed post saves: 1
- Feed post comments: 7
- Stories: 1
- Proof items: 0
- Reports: 0
- AI core memory: 21
- AI feed learning: 1
- Verification codes: 9
- Login attempts: 5
- Security events: 1000
- News items: 0
- Realtime presence: 2
- Realtime typing: 1
- Call signals: 4
- Push devices: 0

## Import Order

1. Users and settings.
2. Social graph and safety relationships.
3. Notifications and messages.
4. Feed posts and feed interactions.
5. Stories, proof, reports, AI, verification, security, news, realtime, and calls.

## Next Step

The private SQL artifact has been generated and applied to staging. All 32 required
tables and every planned row count passed `check_postgres_staging.py --verify-data`.
Keep the verified backup set and repeat this gate before any external production
cutover.
