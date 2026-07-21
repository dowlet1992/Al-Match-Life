CREATE TABLE IF NOT EXISTS call_push_deliveries (
    event_id TEXT NOT NULL REFERENCES call_push_outbox(event_id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES push_devices(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'delivered', 'invalid_token', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attempt_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    last_error_code TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (event_id, device_id)
);
CREATE INDEX IF NOT EXISTS idx_call_push_deliveries_pending
    ON call_push_deliveries(event_id, available_at) WHERE status = 'pending';
