# Web architecture

## Rendering model

Flask remains the source of truth for routing, authentication, authorization,
CSRF validation, and initial server-side rendering. Authenticated navigation
is progressively enhanced by `static/app-shell.js`:

- same-origin links are fetched and committed through the History API;
- forms are submitted as `FormData` with same-origin credentials;
- complete server-rendered HTML remains the fallback when JavaScript is off;
- external links, downloads, static/media assets, and call pages retain native
  browser navigation;
- fetched scripts run only with the nonce already authorized by the current
  page CSP.

This avoids duplicate JSON-only routes while legacy pages are migrated.

## Template rules

New pages must:

1. extend `frontend/base.html`;
2. keep markup in `frontend/*.html`;
3. keep reusable styles and behavior in `static/`;
4. use `translation_bundle` and expose maintained web UI choices as RU/EN/DE;
5. use POST/PATCH/DELETE plus CSRF for mutations;
6. preserve a functional non-JavaScript server response.

Migrated legacy pages currently include:

- shared/simple pages;
- avatar and media management;
- account verification and login 2FA;
- password recovery and password reset;
- AI Assistant.
- blocked-user management;
- hashtag result pages.
- notifications;
- onboarding.
- privacy and AI controls.
- proof profile and proof creation.
- message forwarding selection.
- story viewer.
- news publishing and listing.
- administrator moderation.
- AI matches, people search, and NOVIX Radar.
- friends, followers, following, and friend requests.
- blocked-profile state.
- main profile page shell and styling.
- profile action view models and CSP-safe interactions.
- profile posts, media, tabs, stats, and information view models.
- profile reports and QR display.

Profile QR codes are generated locally and contain the canonical profile URL.
No profile URL or email is sent to an external QR service.

The login entry page uses static CSS/JavaScript and contains no inline event
handlers.

Remaining `render_template_string` pages are migration debt and should be moved
one blueprint at a time, with route tests retained during each move.

## Media

Uploaded media is stored as files and served through `/media-files/<filename>`.
The endpoint uses Werkzeug conditional responses, advertises byte ranges, and
therefore supports browser video/audio seeking without Base64 payloads.

## AI

Text generation depends on the `AIProvider` interface. The default provider is
local Ollama; changing the model requires configuration rather than route
changes. AI Radar is not generative: it uses deterministic profile signals and
the matching/recommendation pipeline.
