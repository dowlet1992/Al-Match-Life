CREATE TABLE IF NOT EXISTS push_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('android', 'ios', 'web')),
    token TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    app_version TEXT NOT NULL DEFAULT '',
    locale TEXT NOT NULL DEFAULT '',
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, device_id)
);
CREATE INDEX IF NOT EXISTS idx_push_devices_active_user
    ON push_devices(user_id, last_seen_at DESC) WHERE revoked_at IS NULL;
