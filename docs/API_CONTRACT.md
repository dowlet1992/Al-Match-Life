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
  - Returns authenticated user, `access_token`, `token_type=Bearer`, `expires_in`, `refresh_token`, and `refresh_expires_in` when verified.
  - Returns `verification_required` when the account still needs verification.

- `POST /api/auth/verify`
  - Verifies account or 2FA code.
  - Body: `purpose`, `contact_type`, `contact_value`, `code`.
  - Supported purposes: `account_verify`, `login_2fa`, `password_reset`.
  - Returns access and refresh tokens for account verification or login 2FA.

- `POST /api/auth/refresh`
  - Atomically rotates a refresh token and returns a new access/refresh token pair.
  - Body: `refresh_token`.
  - A reused or revoked refresh token returns `401`; reuse revokes the complete token family for that device session.

- `POST /api/auth/logout`
  - Ends the active session/token.
  - Optional body: `refresh_token`, used to revoke its complete refresh-token family.
  - Clears the Flask session. When called with a valid Bearer token, rotates the account session version and immediately invalidates previously issued access tokens.

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
  - Returns the logged-in user profile plus authoritative `followers_count` and `following_count` in `social`.
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

- `GET /api/users/{email}/relationship`
  - Returns the authenticated viewer's relationship to that profile: `is_self`, `is_following`, `follows_you`, `is_mutual`, `followers_count`, and `following_count`.
  - A blocked relationship returns `403` without exposing social-graph state.
- `GET /api/users/{email}/followers?limit=20&cursor=...`
- `GET /api/users/{email}/following?limit=20&cursor=...`
  - Return privacy-filtered profile cards with the authenticated viewer's relationship state for each card.
  - `limit` is restricted to `1..50`; `next_cursor` is an opaque URL-safe continuation token. Invalid cursors fail with `400` instead of falling back to the first page.
  - Private, friends-only, deactivated, and blocked profiles follow the same access policy as profile viewing. Blocked/deactivated entries are not exposed. Responses are `private, no-store`.
- `POST /api/users/{email}/follow`
- `DELETE /api/users/{email}/follow`
- Follow and unfollow are idempotent. Their responses include `changed` plus the same authoritative relationship state, so clients never need to guess or optimistically invent counters.
- `followers_count` means accounts following the profile; `following_count` means accounts the profile follows. A mutual follow remains two independent directed relationships.
- Follow mutations are atomic per edge: JSON development mode serializes read-modify-write under one repository lock; PostgreSQL uses targeted `INSERT ... ON CONFLICT DO NOTHING` and `DELETE ... RETURNING` statements rather than replacing the social graph.
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
  - Body: `show_in_search`, `private_profile`, `ai_recommendations`, `ai_life_radar`, `recommend_my_profile`, `ai_activity_analysis`, `notifications_enabled`, `message_permission`, `auto_translate_messages`, `message_translation_language`, `live_call_captions`, `allow_server_call_transcription`, `auto_translate_call_captions`, `call_spoken_language`, `call_caption_language`.
  - `message_translation_language` accepts `auto` (the interface language) or a supported language code.
  - `call_spoken_language` is independent from `call_caption_language`: `auto` enables provider language detection, while an explicit source improves recognition for a known speaker language.

## Messaging

- `GET /api/chats`
  - Returns chat list for the logged-in user.

- `GET /api/chats/{email}/messages`
  - Returns visible messages with one user.
  - When `auto_translate_messages` is enabled, translates up to the latest 20 incoming messages into the selected language, reuses cached results, and saves new translations in one batch.
  - Response includes `auto_translation.enabled`, `target_language`, and `provider_available` so clients can render an honest state.

- `POST /api/chats/{email}/messages`
  - Sends a text message.
  - Body: `message`, optional `reply_to`.
  - The server detects and stores `source_language`; message payloads keep the original text and cached translations separately.

- `POST /api/chats/{email}/messages/{message_id}/translation`
  - Translates a message for a conversation participant and caches the result by target language.
  - Body: optional `target_language`; defaults to the current user's interface language.
  - Returns `source_language`, `target_language`, `translated_text`, and whether the result came from cache.
  - Returns `503` when the production translation provider is unavailable; the original message is never replaced.

## Live call captions

### Mobile signaling

- `GET /api/mobile/bootstrap`
  - Includes a versioned `speech_translation_contract` shared by Android, iOS, and web: legal engine states/transitions, exact Realtime event names, bounded speech queue/ducking policy, fallback limits, shutdown requirements, and credential/privacy guarantees. Clients must reject unsupported future contract versions rather than guessing behavior.
  - Returns authenticated user bootstrap, enabled call/translation features, honest provider availability, independent UI/spoken/translation languages, and versioned endpoint/timeout/ID limits. It never returns provider keys or tokens.
- `GET /api/calls/room`
  - Query: `other_email`, `call_type`. Returns the canonical authorized `call_id`; native clients do not reproduce server filename-normalization rules.

- `GET /api/calls/{call_id}/signals`
  - Bearer-authenticated polling for Android/iOS. Query: `other_email`, `call_type`, optional `after`.
  - Returns only remote signals plus delivery acknowledgments for locally sent event IDs, room status, and server time.
- `POST /api/calls/{call_id}/signals`
  - Body: `other_email`, `call_type`, `type`, `event_id`, and validated `payload`.
  - Uses the same atomic state machine, per-type rate limits, idempotency rules, ephemeral-data purge, call history, and transactional incoming/cancellation push as web signaling.
- `POST /api/calls/{call_id}/signals/ack`
  - Body: `other_email`, `call_type`, and 1–50 `event_ids` successfully processed by the native WebRTC client.
  - Bearer clients do not use CSRF; cookie clients must provide the normal CSRF header.

Native clients resolve the deterministic room ID through `/api/calls/room`, retry one logical signal using the identical `event_id`, ACK only after WebRTC processing succeeds, and retain a bounded deduplication set across app foreground/background transitions.

The web call screen exposes a `CC` control only as an opt-in action. It uses the browser Speech Recognition capability when available, displays interim local text without storing it, and publishes only finalized text segments. Unsupported browsers keep the call working and show an explicit availability message.

Call signaling accepts at most 64 KiB per JSON request. SDP is limited to 32 KiB with matching offer/answer type; ICE candidates are limited to 2 KiB with bounded mid, line index, and username fragment. Atomic per-participant room limits allow 120 ICE candidates and 10 offer/answer events per minute; terminal events are limited to six. Polling is limited to 120 requests per minute per participant/room and returns `429` with `Retry-After` when exceeded.

Signal transitions are validated atomically under the room lock. A new session must begin with `ringing`; only its sender may offer, only its recipient may accept/answer/decline, ICE requires an existing offer, and empty rooms cannot be ended. Closed deterministic rooms can reopen only through a fresh `ringing`. `missed` is server-generated and is rejected from the public signaling endpoint. Invalid transitions return `409 invalid_call_transition` and are audit logged without SDP/ICE content.

Every signaling POST requires a client-generated `event_id` containing 16–80 URL-safe characters. The response echoes `event_id` and returns `duplicate=true|false`. A retry with the same ID and identical type/direction/payload is detected atomically before state validation and rate counting, returns success, and never appends a second event or duplicates call-history side effects. Reusing the ID with different content returns `409 signal_idempotency_conflict`. Browsers retry temporary network/5xx failures up to three times with the exact same serialized body and exponential delay.

`POST /call_signal/{call_id}/ack` accepts `other_email`, `call_type`, and 1–50 unique event IDs. Only the signal recipient may acknowledge an ID; repeated ACKs preserve the original timestamp and return success. Polling always redelivers an unacknowledged addressed event even when it is older than the cursor, and separately returns up to 100 acknowledged IDs for the sender. The browser marks an ID processed only after successful WebRTC handling, retries failed ACK delivery, and acknowledges terminal state before leaving the call page.

Every authorized signal poll atomically evaluates the selected room before delivery. A ringing call without `accepted` expires as server-generated `missed` after 45 seconds; a call with `accepted` but no `answer` expires as `ended` with `negotiation_timeout` after 30 seconds. Timeout IDs are deterministic, transitions are idempotent under the room lock, temporary captions/quality samples are purged, and one call-history event is emitted by the request that wins the transition.

- `GET /api/calls/{call_id}/ice-servers`
  - Query: `other_email`, `call_type` (`audio` or `video`). Authentication, exact participant-room derivation, block, and restriction checks are required.
  - Returns filtered short-lived STUN/TURN configuration. Twilio credentials use a one-hour TTL and a per-user/per-room server cache shorter than that TTL; permanent Account SID/Auth Token values are never returned.
  - Responses use `Cache-Control: no-store, private`. If TURN is not configured or temporarily unavailable, the endpoint fails gracefully to STUN-only configuration and reports `provider=stun_fallback`.

- `POST /api/calls/{call_id}/quality`
  - Accepts only bounded aggregate `rtt_ms`, `jitter_ms`, `packet_loss_percent`, `bitrate_kbps`, and `relay`; no media, SDP, ICE address, device identifier, or raw stats report is retained.
  - The server derives `good`/`fair`/`poor`, accepts at most one sample per participant every four seconds, and retains only the latest 24 samples in an active room. Samples are purged immediately on ended, declined, or missed.

- `GET /api/admin/calls/quality`
  - Admin-only aggregate for retained active/recent call rooms: connection success rate, room/status counts, TURN room rate, fixed end-reason counts, quality distribution, and room-level p50/p95 RTT, jitter, loss, and bitrate.
  - Returns no room IDs, participant identifiers, timestamps, signal payloads, or individual samples. Viewing the aggregate emits a security audit event.

- `POST /api/calls/{call_id}/captions`
  - Publishes one already-recognized speech segment for an active audio/video call.
  - Body: `other_email`, `call_type`, `text`, optional `source_language`, `is_final`, and `sequence`.
  - Requires `live_call_captions=true`; accepts text only and never uploads or stores raw audio.

- `GET /api/calls/{call_id}/captions`
  - Polls remote-speaker segments using `other_email`, `call_type`, and optional `after` timestamp.
  - Only authenticated room participants can publish or poll. Blocked/restricted relationships are rejected.
  - Segments are capped per room and expire after six hours while a call is open. Captions and transcription reservations are purged immediately when a call is ended, declined, or marked missed; this endpoint is temporary realtime transport, not permanent transcript storage.
  - Segment publication is atomic per room for JSON and PostgreSQL storage, preventing concurrent speakers from overwriting each other's captions.
  - Closed signaling rooms remain available for final-state delivery for 24 hours, then are removed. Abandoned non-terminal rooms expire after seven days; an active recently updated room is never removed. Signaling events are retained for 24 hours and capped at 300 per room.

- `POST /api/calls/{call_id}/captions/{caption_id}/translation`
  - Translates one authorized caption without replacing its original text.
  - Body: `other_email`, `call_type`, optional `target_language`; the user's call-caption language is used by default.
  - Translation runs separately from caption delivery and is atomically cached by language, so a slow provider never blocks the original realtime caption.

- `POST /api/calls/{call_id}/captions/transcribe`
  - Server fallback for clients without browser-native speech recognition.
  - Requires both `live_call_captions=true` and the separate `allow_server_call_transcription=true` consent because audio bytes are sent to the configured external AI provider.
  - Granting consent records `server_transcription_consent_at`; revoking it preserves that timestamp and records `server_transcription_consent_revoked_at`. Grant/revoke transitions are written to the security audit log, while ordinary settings saves do not rewrite consent history.
  - Multipart body: `audio`, `other_email`, `call_type`, optional `source_language` and `sequence`.
  - Accepts only allowlisted audio MIME types and at most 2 MiB per chunk. Bytes are processed in memory, sent to the configured transcription provider, never written to disk, and never stored in the call room.
  - The complete multipart request is rejected with `413` before form parsing when it exceeds the audio limit plus bounded multipart overhead. The server also validates the container signature (WebM/EBML, Ogg, WAV, MP4, or MP3) instead of trusting the client MIME header.
  - The default provider model is configurable with `OPENAI_TRANSCRIPTION_MODEL` and defaults to `gpt-4o-mini-transcribe`.
  - Every chunk requires a positive, monotonically increasing client `sequence`. The server atomically reserves `(room, speaker, sequence)` before provider usage, rejects duplicates with `409`, and limits each speaker to 18 chunks per rolling minute with `429`.
  - Rate-limit responses include `Retry-After`. Clients must back off, ignore confirmed duplicates, and suspend local server recording after repeated provider failures while continuing to poll remote captions.

- `POST /api/calls/{call_id}/translation/realtime-session`
  - Creates a short-lived OpenAI Realtime transcription credential for an authenticated participant in an accepted/active call. The permanent provider key never leaves the server.
  - Requires both live-caption and server-transcription consent, uses the user's explicit spoken language when configured, is rate-limited, and returns `Cache-Control: no-store`.
  - The response includes the fixed provider calls endpoint, Realtime model, transcription model, transport, expiry, and ephemeral secret. Native/web clients exchange multipart SDP, send microphone audio through an isolated WebRTC peer, consume incremental/final transcription events, and publish authorized caption text through the existing caption contract. The multipart endpoint remains the degraded-network fallback.

- `POST /api/calls/{call_id}/captions/{caption_id}/speech`
  - Translates and synthesizes only a remote participant's authorized caption; arbitrary public TTS input is not accepted.
  - Requires separate `allow_ai_voice_translation` consent and an accepted/active call. Only built-in synthetic voices are allowlisted; custom or cloned voices are rejected.
  - The first successful translation is atomically cached on its authorized caption before TTS, so repeated playback does not repeat translation-provider work. A failed concurrent caption update aborts synthesis rather than speaking untracked text.
  - Returns bounded in-memory MP3 with `Cache-Control: no-store`, `X-AI-Generated-Voice: true`, `X-AI-Voice`, `X-Caption-Id`, and `Content-Language`. Audio is never persisted.

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
- Bearer tokens are bound to the account session version and are rejected after logout, password change, deactivation, or a security-driven session rotation.
- Refresh tokens are stored only as hashes, rotate on every use, and use family-wide revocation when reuse is detected.
- Runtime data should move from JSON files to database tables before public launch.

## Push Devices

All endpoints require the authenticated account. Raw provider tokens and token hashes are accepted only during registration and are never returned.

- `GET /api/push/devices` lists the current account's active devices using safe metadata only.
- `GET /api/push/config` returns only authenticated Web Push bootstrap metadata and the public VAPID key, never private provider material.
- `POST /api/push/devices` registers or refreshes one device. JSON body: `platform` (`android`, `ios`, or `web`), stable `device_id`, provider `token`, and optional `app_version` and `locale`.
- `DELETE /api/push/devices/<device_id>` revokes one device owned by the current account and is idempotent.

Reusing a provider token transfers it atomically to the latest authenticated device registration. Account deletion revokes every registered device. PostgreSQL production uses the `push_devices` table; JSON remains a development fallback.

An accepted `ringing` signaling event creates an `incoming_call` outbox record inside the same repository lock or PostgreSQL transaction. The client-generated signaling `event_id` is also the outbox primary key, so retries cannot enqueue duplicate pushes. Outbox payloads contain call context but never provider tokens; token lookup happens only during delivery.

Production delivery snapshots active devices into durable `call_push_deliveries` receipts. Receipt identity is `(event_id, device_id)`: delivered devices are terminal, invalid devices are revoked and terminal, and only temporarily failed devices receive another attempt. Provider tokens remain in `push_devices` and are resolved at send time rather than copied into receipts.

Cookie-authenticated device writes require CSRF. Bearer-authenticated native clients use their access-token protection. The root-scope web service worker validates participant addresses, rejects malformed or expired call payloads, displays privacy-safe generic call text, and opens only the authenticated internal chat route.
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
