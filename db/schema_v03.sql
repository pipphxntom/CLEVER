-- v0.3 additive schema. Apply after schema.sql and schema_novel.sql.

ALTER TABLE request_log
    ADD COLUMN IF NOT EXISTS request_id UUID,
    ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS usage_legs JSONB,
    ADD COLUMN IF NOT EXISTS stakes_reason TEXT,
    ADD COLUMN IF NOT EXISTS query_text_redacted TEXT;

CREATE INDEX IF NOT EXISTS request_log_ts_idx ON request_log (ts DESC);
CREATE INDEX IF NOT EXISTS request_log_intent_ts_idx ON request_log (intent, ts DESC);
CREATE INDEX IF NOT EXISTS request_log_stakes_idx ON request_log (ts DESC) WHERE stakes_reason IS NOT NULL;
CREATE INDEX IF NOT EXISTS request_log_ras_idx ON request_log (ts DESC) WHERE ras_gate_fired IS NOT NULL;

CREATE TABLE IF NOT EXISTS faq_candidates (
    id         BIGSERIAL PRIMARY KEY,
    query_hash TEXT UNIQUE,
    frequency  INT,
    status     TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT now()
);
