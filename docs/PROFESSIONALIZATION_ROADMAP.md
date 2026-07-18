# Professionalization Roadmap

This roadmap tracks the work required to move AI Match Life from a strong web prototype to a professional production platform.

## 1. Architecture

- Split the large `app.py` into clear modules.
- Separate routes, services, storage, AI logic, and rendering.
- Keep changes incremental so the working product does not break.
- Started: API serializers moved to `backend/serializers.py`.
- Started: feed business logic moved to `backend/services/feed_service.py`.
- Started: message business logic moved to `backend/services/message_service.py`.
- Started: social business logic moved to `backend/services/social_service.py`.
- Started: profile business logic moved to `backend/services/profile_service.py`.
- Started: privacy rules moved to `backend/services/privacy_service.py`.
- Started: API blueprint package created in `backend/api/`; `/api/health` moved to `backend/api/system.py`.
- Started: Auth API moved to `backend/api/auth.py` with dependency injection.
- Started: Profile and Privacy API moved to `backend/api/profile.py` with dependency injection.
- Started: Feed API moved to `backend/api/feed.py` with dependency injection.
- Started: Messages API moved to `backend/api/messages.py` with dependency injection.
- Started: Social API moved to `backend/api/social.py` with dependency injection.
- Started: Notifications API moved to `backend/api/notifications.py` with dependency injection.
- Started: Matches API moved to `backend/api/matches.py` with dependency injection.
- Started: Repository layer created in `backend/repositories/` with atomic JSON writes.
- Started: Feed and notifications storage now use `JsonStore`.
- Started: Messages storage moved to `backend/messages.py` backed by `JsonStore`.
- Started: Login attempts, security log, and verification codes moved behind repository-backed backend modules.
- Started: Social graph storage moved to repository-backed `backend/social.py`.
- Started: Privacy and proof storage moved behind repository-backed backend modules.
- Started: Typing and presence status storage moved to repository-backed `backend/realtime_status.py`.
- Started: Stories, blocks, reports, restrictions, and hidden stories moved behind repository-backed backend modules.
- Started: AI core memory and AI feed learning moved to repository-backed `backend/ai_memory_store.py`.
- Started: News and call signal storage moved behind repository-backed backend modules.
- Started: User AI settings moved to dedicated repository-backed storage with legacy privacy-data fallback.
- Complete: direct JSON reads/writes have been removed from `app.py`.
- Started: User and language storage now use repository-backed backend modules.
- Started: Initial PostgreSQL schema added in `database/migrations/001_initial_schema.sql`.
- Started: JSON-to-database mapping documented in `docs/JSON_TO_DATABASE_MAPPING.md`.
- Started: JSON migration inventory script added in `scripts/json_migration_inventory.py`.
- Started: Current dry-run data report documented in `docs/MIGRATION_DRY_RUN_REPORT.md`.
- Complete: Orphan JSON references to missing users cleaned with backup support in `scripts/clean_orphan_user_refs.py`.
- Started: JSON import plan script added in `scripts/build_json_import_plan.py`.
- Started: Current import plan documented in `docs/JSON_IMPORT_PLAN_REPORT.md`.
- Started: PostgreSQL import SQL generator added in `scripts/export_json_to_postgres_sql.py`.
- Started: Generated import artifacts are ignored by git and summarized in `docs/POSTGRES_IMPORT_SQL_REPORT.md`.
- Started: Database readiness config and check script added for safe JSON/PostgreSQL transition.
- Started: PostgreSQL staging verification script added for connection and required schema table checks.
- Started: Safe PostgreSQL schema apply script added with dry-run default and explicit `--apply`.
- Started: Safe PostgreSQL import apply script added with dry-run default and explicit `--apply`.
- Started: Staging migration orchestrator added to show the full migration order and blockers in one report.
- Started: Users now have JSON and PostgreSQL repository implementations behind existing storage functions.
- Started: Messages now have JSON and PostgreSQL repository implementations behind existing storage functions.
- Started: Social graph now has JSON and PostgreSQL repository implementations behind existing social functions.
- Started: Feed now has JSON and PostgreSQL repository implementations behind existing feed functions.
- Started: Notifications and privacy settings now have JSON and PostgreSQL repository implementations.
- Started: Stories, proof items, and AI memory now have JSON and PostgreSQL repository implementations.
- Started: Security, realtime status, and call signals now have JSON and PostgreSQL repository implementations.
- Started: News and user AI settings now have JSON and PostgreSQL repository implementations.
- Started: Social safety data now has JSON and PostgreSQL repository implementations for blocks, reports, restrictions, and hidden story authors.
- Started: Production environment readiness check added for secrets, database mode, verification providers, 2FA, and AI configuration.
- Started: Moderation service added for report creation, status workflow, reviewer metadata, summaries, and PostgreSQL report export.
- Started: Admin moderation API added for report list, filtering, summaries, and status updates via `ADMIN_EMAILS`.
- Started: Admin moderation HTML page added for reviewing and updating user reports.
- Started: Dashboard shows the moderation entry only for configured administrator emails.
- Started: Dashboard and settings received a professional UI pass with cleaner navigation, calmer controls, and tighter radii.
- Started: Mobile token auth foundation added with signed Bearer access tokens for login, verification, and `/api/me`.
- Started: Unified i18n foundation added for language detection, translation bundles, and dashboard/settings localized rendering.
- Started: Login and registration pages now localize from browser/device language before account creation.
- Next: apply generated SQL to a staging database, then run repository integration checks against PostgreSQL/Supabase.

## 2. Database

- Move runtime data from JSON files to PostgreSQL or Supabase.
- Add migrations and import scripts.
- Keep JSON backups during the transition.

## 3. Mobile API

- Complete JSON APIs for auth, profile, onboarding, matches, social, feed, messages, notifications, privacy.
- Keep web session support for browser users.
- Started: Add token-based auth before the mobile app beta.

## 4. Tests

- Cover auth, registration, profile, onboarding, matches, social, messages, privacy, notifications.
- Keep core backend logic testable without a running server.

## 5. Mobile App

- Build with React Native / Expo after the API contract is stable.
- Start with auth, onboarding, matches, profile, chat, feed.

## 6. Admin And Moderation

- Add admin panel for users, reports, blocked content, proof review, trust review.
- Add audit logs and moderation statuses.
- Started: Report moderation workflow supports `new`, `reviewing`, `resolved`, and `dismissed` statuses.
- Started: Admin moderation API protects report actions behind configured administrator emails.
- Started: Admin moderation page provides counters, filters, and CSRF-protected report status forms.
- Started: Admin dashboard navigation now exposes moderation tools only to administrators.

## 7. AI Learning

- Improve learning from onboarding, profile edits, feed actions, matches, messages, language, location, and privacy settings.
- Keep AI recommendations explainable.

## 8. Design System

- Unify layout, spacing, colors, buttons, forms, cards, navigation, empty states, and mobile behavior.
- Keep the product serious, premium, and easy to scan.
- Started: Dashboard/settings navigation and controls moved toward a cleaner working-product design.
- Started: Dashboard and settings now use shared i18n keys for core labels and respect browser/device language headers.
- Started: Post-registration onboarding now uses shared i18n keys for core AI matching questions.

## 9. Production Deployment

- Add production config, environment validation, logging, backups, health checks, deployment docs, and security review.
- Started: `scripts/check_production_readiness.py` validates production environment settings before deploy.

## Current Priority

1. Complete API foundation.
2. Expand tests.
3. Prepare database migration.
4. Improve onboarding and AI learning.
5. Start mobile app after API stability.
