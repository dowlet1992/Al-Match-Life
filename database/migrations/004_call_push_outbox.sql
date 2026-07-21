CREATE TABLE IF NOT EXISTS call_push_outbox (
    event_id TEXT PRIMARY KEY,
    target_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    room_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('incoming_call', 'call_cancelled')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'delivered', 'failed', 'expired')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    locked_at TIMESTAMPTZ,
    last_error_code TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_call_push_outbox_due
    ON call_push_outbox(available_at, created_at)
    WHERE status = 'pending';
