-- CLEVER Novel Layers Schema Additions

-- aging_data: loaded from real .xlsx
CREATE TABLE IF NOT EXISTS aging_data (
    id            BIGSERIAL PRIMARY KEY,
    aging_version TEXT REFERENCES data_versions(version),
    account_id    TEXT,
    account       TEXT,
    balance       NUMERIC(14,2),
    days_overdue  INT,
    status        TEXT,
    contact       TEXT,
    invoice_ids   TEXT[],
    last_contact  DATE,
    raw           JSONB
);
CREATE INDEX IF NOT EXISTS aging_data_account_idx
    ON aging_data (account_id, aging_version);

-- faq_entries: BM25 knowledge base
CREATE TABLE IF NOT EXISTS faq_entries (
    id         BIGSERIAL PRIMARY KEY,
    question   TEXT UNIQUE,
    answer     TEXT,
    source     TEXT DEFAULT 'manual',
    hit_count  INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS faq_entries_ts_idx
    ON faq_entries
    USING gin(to_tsvector('english', question || ' ' || answer));

-- vpt_daily: daily VpT aggregates
CREATE TABLE IF NOT EXISTS vpt_daily (
    date         DATE,
    intent       TEXT,
    avg_vpt      NUMERIC(12,6),
    total_tokens BIGINT,
    total_value  NUMERIC(12,4),
    PRIMARY KEY (date, intent)
);

-- Add VpT + RAS columns to request_log
ALTER TABLE request_log
    ADD COLUMN IF NOT EXISTS vpt               NUMERIC(12,6),
    ADD COLUMN IF NOT EXISTS outcome_unit      TEXT,
    ADD COLUMN IF NOT EXISTS outcome_value_usd NUMERIC(12,6),
    ADD COLUMN IF NOT EXISTS outcome_count     INT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS ras_gate_fired    TEXT,
    ADD COLUMN IF NOT EXISTS route_class       TEXT;
