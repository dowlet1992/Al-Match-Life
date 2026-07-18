# Mobile Readiness Plan

## Current cleanup focus

- Keep one canonical implementation for social actions.
- Add reproducible project dependencies in `requirements.txt`.
- Add baseline tests for risky shared backend logic.
- Remove plaintext legacy passwords from local JSON data.
- Keep web MVP stable before extracting a mobile API.

## Before mobile app development

1. Finish AI onboarding after registration.
2. Add API routes for auth, profile, matches, feed, messages, notifications.
3. Move JSON storage to a real database.
4. Add tests for auth, profile, matches, privacy, messages.
5. Prepare mobile screens in React Native / Expo after the API contract is stable.

## Started

- API login and account verification now return signed `Bearer` access tokens for mobile clients.
- API current-user lookup accepts `Authorization: Bearer <access_token>`.
- Web sessions continue to work for browser users.
- Token revocation and refresh tokens are still planned before public mobile beta.
- Shared i18n foundation now supports automatic UI language from browser/device language headers for the first core screens.
- Login and registration screens now use the shared i18n foundation before a user account exists.
- Post-registration onboarding now uses the same language foundation for goals, interests, skills, languages, and AI Matches prompts.
- Public `GET /api/i18n` startup endpoint now returns device-language negotiation, fallback metadata, supported language catalog, text direction, and translation bundle for mobile clients.
- Public `POST /api/i18n/language` now saves a supported UI language preference and rejects planned languages until translations are production-ready.
- Language negotiation now respects device/browser priority and `q` quality values before falling back.
- Spanish and French are now supported startup UI languages for login, registration, settings, dashboard navigation, onboarding, and `/api/i18n`.
- Portuguese and Italian are now supported startup UI languages for login, registration, settings, dashboard navigation, onboarding, and `/api/i18n`.
- Hindi and Indonesian are now supported startup UI languages for login, registration, settings, dashboard navigation, onboarding, AI Discover, and `/api/i18n`.
- Chinese and Japanese are now supported startup UI languages for login, registration, settings, dashboard navigation, onboarding, AI Discover, and `/api/i18n`.
- Korean is now a supported startup UI language for login, registration, settings, dashboard navigation, onboarding, AI Discover, and `/api/i18n`.
- Polish and Dutch are now supported startup UI languages for login, registration, settings, dashboard navigation, onboarding, AI Discover, and `/api/i18n`.
- Ukrainian and Romanian are now supported startup UI languages for login, registration, settings, dashboard navigation, onboarding, AI Discover, and `/api/i18n`.
- Arabic is now a supported startup UI language with `rtl` direction metadata for mobile clients.
- Translation coverage checks now prevent a language from being treated as production-ready if required startup keys are missing.
- `/api/i18n` now exposes translation completion percent for requested, supported, and catalog languages.
- AI Discover legacy UI strings are now synchronized for all supported startup languages.
- `backend/i18n.py` is now the single source of truth for supported UI languages and the global content language catalog.
- A global language catalog now exposes native language names, direction, and translation status so mobile can scale toward broad Instagram-style language coverage without pretending unfinished translations are ready.
