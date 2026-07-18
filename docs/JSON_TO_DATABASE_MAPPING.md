# JSON To Database Mapping

This document maps the current repository-backed JSON stores to the PostgreSQL schema in `database/migrations/001_initial_schema.sql`.

## Account And Profile

- `users.json` -> `users`
- `database/user_ai_settings.json` -> `user_ai_settings`
- `database/privacy_data.json` -> `privacy_settings`

## Social Graph And Safety

- `social.json.follows` -> `social_follows`
- `social.json.friends` -> `friendships`
- `social.json.friend_requests` -> `friend_requests`
- `blocks.json` -> `user_blocks`
- `restrictions.json` -> `user_restrictions`
- `hidden_stories.json` -> `hidden_story_authors`
- `reports.json` -> `reports`

## Communication

- `messages.json` -> `messages`
- `notifications.json` -> `notifications`
- `typing_status.json` -> `realtime_typing`
- `presence_status.json` -> `realtime_presence`
- `call_signals.json` -> `call_signals`

## Content

- `database/feed_data.json.posts` -> `feed_posts`
- `post.likes` -> `feed_post_likes`
- `post.saves` -> `feed_post_saves`
- `post.comments` -> `feed_post_comments`
- `stories.json` -> `stories`
- `database/proof_data.json` -> `proof_items`
- `news.json` -> `news_items`

## AI And Security

- `ai_core_memory.json` -> `ai_core_memory`
- `ai_feed_learning.json` -> `ai_feed_learning`
- `verification_codes.json` -> `verification_codes`
- `login_attempts.json` -> `login_attempts`
- `security_log.json` -> `security_events`

## Migration Rules

- Resolve users by normalized email before inserting dependent records.
- Keep unknown or missing users out of relationship tables and write them to an import error report.
- Store list-heavy fields as JSONB first; normalize later only when query needs are clear.
- Convert legacy timestamp strings to `TIMESTAMPTZ` during import.
- Keep JSON backups read-only until database import is verified.
