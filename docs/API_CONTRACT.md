# AI Match Life API Contract

This is the mobile-ready API direction. The current product is a Flask web app; mobile should use JSON API endpoints instead of scraping HTML pages.

## Auth

- `POST /api/auth/register`
  - Creates a user and starts account verification.
  - Body: `name`, `age`, `country`, `contact_type`, `email`, `phone`, `password`.
  - Returns: `verification_required`, `delivery_sent`, `contact_type`, `contact_value`, `user`.

- `POST /api/auth/login`
  - Starts a session or returns a 2FA challenge.
  - Body: `login`, `password`.
  - Returns authenticated user, `access_token`, `token_type=Bearer`, and `expires_in` when verified.
  - Returns `verification_required` when the account still needs verification.

- `POST /api/auth/verify`
  - Verifies account or 2FA code.
  - Body: `purpose`, `contact_type`, `contact_value`, `code`.
  - Supported purposes: `account_verify`, `login_2fa`, `password_reset`.
  - Returns `access_token`, `token_type=Bearer`, and `expires_in` for account verification or login 2FA.

- `POST /api/auth/logout`
  - Ends the active session/token.
  - Current implementation clears the Flask session. Mobile access tokens expire naturally; token revocation storage is planned.

## Internationalization

- `GET /api/i18n`
  - Public startup endpoint for web and mobile clients.
  - Reads `Accept-Language` from the browser/device or optional `?lang=<code>` override.
  - Respects browser/device language priority and quality values, so a supported secondary language can be selected when the primary language is not translated yet.
  - Returns selected UI language, requested device language, native language names, translation status, translation completion percent, fallback language, text direction, supported language catalog, global language catalog, and the current translation bundle.
  - Current startup UI languages: `ru`, `en`, `es`, `fr`, `pt`, `it`, `de`, `hi`, `id`, `zh`, `ja`, `ko`, `pl`, `nl`, `uk`, `ro`, `tr`, `ar`; Arabic returns `direction=rtl`.
  - The global language catalog lets mobile clients recognize many device languages even before full UI translation is completed.
  - If the device language is not translated yet, the response keeps `requested_language` and returns the safe default UI language as `fallback_language`.

- `POST /api/i18n/language`
  - Saves a supported UI language preference into the web session and returns locale metadata plus translations.
  - Body: `language`.
  - Planned or unknown languages are rejected as production UI preferences until their required translations are complete.

## Profile

- `GET /api/me`
  - Returns the logged-in user profile.
  - Accepts web session auth or `Authorization: Bearer <access_token>`.

- `PATCH /api/me/profile`
  - Updates profile fields used for AI matching.
  - Body: `bio`, `profession`, `looking_for`, `languages`, `goals`, `interests`, `skills`.

- `POST /api/me/onboarding`
  - Saves onboarding answers and marks profile readiness.

## Matching

- `GET /api/matches`
  - Returns ranked AI matches with score, level, and reasons.

- `GET /api/radar`
  - Returns broader AI Radar recommendations.

## Social

- `POST /api/users/{email}/follow`
- `DELETE /api/users/{email}/follow`
- `POST /api/users/{email}/friend-request`
- `POST /api/users/{email}/friend-request/accept`
- `POST /api/users/{email}/friend-request/decline`

## Notifications

- `GET /api/notifications`
  - Returns notifications for the logged-in user.

## Privacy

- `GET /api/privacy`
  - Returns privacy and AI settings for the logged-in user.

- `PATCH /api/privacy`
  - Updates privacy and AI settings.
  - Body: `show_in_search`, `private_profile`, `ai_recommendations`, `ai_life_radar`, `recommend_my_profile`, `ai_activity_analysis`, `notifications_enabled`, `message_permission`.

## Messaging

- `GET /api/chats`
  - Returns chat list for the logged-in user.

- `GET /api/chats/{email}/messages`
  - Returns visible messages with one user.

- `POST /api/chats/{email}/messages`
  - Sends a text message.
  - Body: `message`, optional `reply_to`.

## Feed

- `GET /api/feed`
  - Returns visible feed posts for the logged-in user.

- `POST /api/feed/posts`
  - Creates a text post.
  - Body: `type`, `text`, `location`, `hashtags`, `language`.
  - Media upload endpoint is planned separately.

- `POST /api/feed/posts/{post_id}/like`
  - Toggles like on a post.

- `POST /api/feed/posts/{post_id}/comment`
  - Adds a comment to a post.
  - Body: `text`.

- `POST /api/feed/posts/{post_id}/save`
  - Toggles saved state for a post.

## Production rules

- All API responses use JSON.
- All write endpoints require auth and CSRF or token protection.
- Mobile should use `Authorization: Bearer <access_token>`; web can keep cookie sessions.
- Runtime data should move from JSON files to database tables before public launch.
## Admin Moderation

Admin APIs require an authenticated session whose email is listed in `ADMIN_EMAILS`.

- `GET /api/admin/moderation/reports`
  - Optional query: `status`, `target_email`, `reporter_email`
  - Returns moderation `summary` and filtered `reports`.
- `PATCH /api/admin/moderation/reports/<report_id>`
  - Body: `status`, optional `note`, optional `action`
  - Supported statuses: `new`, `reviewing`, `resolved`, `dismissed`
  - Updates reviewer metadata and returns the updated report.

The same workflow is also available as an HTML moderation page:

- `GET /admin/moderation/<admin_email>`
  - Lists reports, counters, filters, and moderation forms.
- `POST /admin/moderation/<admin_email>`
  - Updates one report status with CSRF protection.
