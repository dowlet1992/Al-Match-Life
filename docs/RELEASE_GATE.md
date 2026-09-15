# NOVIX release gate

Run the bounded, read-only release gate immediately before a deployment:

```bash
APP_ENV=production FLASK_ENV=production python3 scripts/release_gate.py --pretty
```

The command exits with `0` only when all required gates pass:

- production configuration and PostgreSQL selection;
- fresh, checksum-valid, restore-verified PostgreSQL backup;
- fresh, checksum-valid, verified user-media backup;
- HTTP security headers and password/authentication source checks;
- consistent installed Python dependencies.

A failure exits with `1` and returns stable machine-readable blocker names. Check
exceptions expose only their class, never connection strings, credentials, raw
command output, or user data. The command is suitable for a CI/CD pre-deployment
step but does not modify application or database state.

Warnings inside `details.production.warnings` are non-blocking for the web
release gate but must still be resolved for the corresponding feature/platform.
For example, Android FCM and iOS APNs are mobile launch requirements, while a
production LiveKit configuration is required before claiming reliable group
calling in the public environment.

## Verified local status

On 2026-09-06 the complete local gate passed all five checks with no blockers:
production PostgreSQL configuration, PostgreSQL backup, media backup, security,
and Python dependencies. The full test suite also passed 992 tests. Remaining
warnings require external credentials or infrastructure: production LiveKit,
Android FCM, and iOS APNs.
