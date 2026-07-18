-- AI Match Life initial PostgreSQL schema.
-- This schema mirrors the current repository-backed JSON model and prepares the
-- project for a controlled migration to PostgreSQL or Supabase.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    phone TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    age INTEGER,
    country TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    profession TEXT DEFAULT '',
    looking_for TEXT DEFAULT '',
    languages JSONB NOT NULL DEFAULT '[]'::jsonb,
    goals JSONB NOT NULL DEFAULT '[]'::jsonb,
    interests JSONB NOT NULL DEFAULT '[]'::jsonb,
    skills JSONB NOT NULL DEFAULT '[]'::jsonb,
    trust_score INTEGER NOT NULL DEFAULT 50,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    profile_completed BOOLEAN NOT NULL DEFAULT FALSE,
    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    onboarding_skipped BOOLEAN NOT NULL DEFAULT FALSE,
    account_verified BOOLEAN NOT NULL DEFAULT TRUE,
    account_verified_at TIMESTAMPTZ,
    account_verified_via TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_country ON users (country);
CREATE INDEX IF NOT EXISTS idx_users_profession ON users (profession);
CREATE INDEX IF NOT EXISTS idx_users_trust_score ON users (trust_score);

CREATE TABLE IF NOT EXISTS user_ai_settings (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    settings JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS privacy_settings (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    receive_recommendations BOOLEAN NOT NULL DEFAULT TRUE,
    show_me_to_others BOOLEAN NOT NULL DEFAULT TRUE,
    show_in_search BOOLEAN NOT NULL DEFAULT TRUE,
    allow_messages BOOLEAN NOT NULL DEFAULT TRUE,
    verified_only_messages BOOLEAN NOT NULL DEFAULT FALSE,
    vip_mode BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS social_follows (
    follower_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    following_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_id, following_id),
    CHECK (follower_id <> following_id)
);

CREATE INDEX IF NOT EXISTS idx_social_follows_following ON social_follows (following_id);

CREATE TABLE IF NOT EXISTS friendships (
    user_low_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_high_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_low_id, user_high_id),
    CHECK (user_low_id <> user_high_id)
);

CREATE TABLE IF NOT EXISTS friend_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (sender_id, receiver_id),
    CHECK (sender_id <> receiver_id),
    CHECK (status IN ('pending', 'accepted', 'declined', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_friend_requests_receiver_status ON friend_requests (receiver_id, status);

CREATE TABLE IF NOT EXISTS user_blocks (
    blocker_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    blocked_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (blocker_id, blocked_id),
    CHECK (blocker_id <> blocked_id)
);

CREATE TABLE IF NOT EXISTS user_restrictions (
    restrictor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    restricted_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restrictor_id, restricted_id),
    CHECK (restrictor_id <> restricted_id)
);

CREATE TABLE IF NOT EXISTS hidden_story_authors (
    viewer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (viewer_id, author_id),
    CHECK (viewer_id <> author_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    type TEXT NOT NULL DEFAULT 'system',
    text TEXT NOT NULL DEFAULT '',
    status TEXT DEFAULT '',
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications (user_id, read);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL DEFAULT '',
    media_url TEXT DEFAULT '',
    media_type TEXT DEFAULT '',
    media_name TEXT DEFAULT '',
    reply_to BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    deleted_for_everyone BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_for JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (sender_id, receiver_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_receiver_created ON messages (receiver_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feed_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT NOT NULL DEFAULT 'Идея',
    text TEXT NOT NULL,
    language TEXT DEFAULT 'unknown',
    location TEXT DEFAULT '',
    hashtags JSONB NOT NULL DEFAULT '[]'::jsonb,
    media JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feed_posts_created ON feed_posts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feed_posts_author_created ON feed_posts (author_id, created_at DESC);

CREATE TABLE IF NOT EXISTS feed_post_likes (
    post_id UUID NOT NULL REFERENCES feed_posts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS feed_post_saves (
    post_id UUID NOT NULL REFERENCES feed_posts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (post_id, user_id)
);

CREATE TABLE IF NOT EXISTS feed_post_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES feed_posts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feed_comments_post_created ON feed_post_comments (post_id, created_at);

CREATE TABLE IF NOT EXISTS stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    media_url TEXT NOT NULL DEFAULT '',
    media_type TEXT DEFAULT '',
    text TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_stories_author_created ON stories (author_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_stories_expires_at ON stories (expires_at);

CREATE TABLE IF NOT EXISTS proof_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type TEXT DEFAULT '',
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    media_url TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    ai_summary TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_proof_items_user_created ON proof_items (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_proof_items_status ON proof_items (status);

CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reporter_id UUID REFERENCES users(id) ON DELETE SET NULL,
    target_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'new',
    reviewed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    moderation_note TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_status_created ON reports (status, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_core_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode TEXT DEFAULT '',
    question TEXT DEFAULT '',
    answer TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_core_memory_user_created ON ai_core_memory (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_feed_learning (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    languages JSONB NOT NULL DEFAULT '{}'::jsonb,
    types JSONB NOT NULL DEFAULT '{}'::jsonb,
    hashtags JSONB NOT NULL DEFAULT '{}'::jsonb,
    locations JSONB NOT NULL DEFAULT '{}'::jsonb,
    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS verification_codes (
    key TEXT PRIMARY KEY,
    contact_type TEXT NOT NULL,
    contact_value TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    code_hash TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verification_codes_contact ON verification_codes (contact_type, contact_value);
CREATE INDEX IF NOT EXISTS idx_verification_codes_expires_at ON verification_codes (expires_at);

CREATE TABLE IF NOT EXISTS login_attempts (
    key TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    attempts JSONB NOT NULL DEFAULT '[]'::jsonb,
    locked_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS security_events (
    id BIGSERIAL PRIMARY KEY,
    event TEXT NOT NULL,
    email TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    details TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_security_events_created ON security_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_events_email_created ON security_events (email, created_at DESC);

CREATE TABLE IF NOT EXISTS news_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    author_name TEXT DEFAULT 'AI Match Life',
    title TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    source TEXT DEFAULT '',
    location TEXT DEFAULT '',
    media JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_items_created ON news_items (created_at DESC);

CREATE TABLE IF NOT EXISTS realtime_presence (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    online BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime_typing (
    sender_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_typing BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (sender_id, receiver_id)
);

CREATE TABLE IF NOT EXISTS call_signals (
    room_id TEXT PRIMARY KEY,
    caller_id UUID REFERENCES users(id) ON DELETE SET NULL,
    receiver_id UUID REFERENCES users(id) ON DELETE SET NULL,
    call_type TEXT NOT NULL DEFAULT 'audio',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
