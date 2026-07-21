-- Operational fixed-window counters shared by every production application instance.
CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    key_hash TEXT NOT NULL,
    category TEXT NOT NULL,
    bucket_start BIGINT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 1 CHECK (request_count > 0),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (key_hash, category, bucket_start)
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_expires ON rate_limit_buckets(expires_at);
