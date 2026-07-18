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
- User AI settings: 0
- Privacy settings: 11
- Social follows: 0
- Friendships: 1
- Friend requests: 0
- User blocks: 0
- User restrictions: 0
- Hidden story authors: 0
- Notifications: 8
- Messages: 24
- Feed posts: 6
- Feed post likes: 3
- Feed post saves: 1
- Feed post comments: 7
- Stories: 1
- Proof items: 0
- Reports: 0
- AI core memory: 8
- AI feed learning: 1
- Verification codes: 7
- Login attempts: 3
- Security events: 221
- News items: 0
- Realtime presence: 3
- Realtime typing: 2
- Call signals: 1

## Import Order

1. Users and settings.
2. Social graph and safety relationships.
3. Notifications and messages.
4. Feed posts and feed interactions.
5. Stories, proof, reports, AI, verification, security, news, realtime, and calls.

## Next Step

Create a database import script that uses this plan, resolves users by normalized email, writes rejected rows to an import error report, and runs inside a transaction.
