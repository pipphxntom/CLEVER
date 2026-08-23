-- v0.5: Thompson routing traces live in decision_trace JSONB (no registry change).
-- Sleep: consolidation_log, richer faq_candidates, query_hash index.

CREATE INDEX IF NOT EXISTS request_log_query_hash_idx
    ON request_log (query_hash)
    WHERE query_hash IS NOT NULL;

CREATE TABLE IF NOT EXISTS consolidation_log (
    id                   BIGSERIAL PRIMARY KEY,
    ts                   TIMESTAMPTZ DEFAULT now(),
    window_start         TIMESTAMPTZ,
    window_end           TIMESTAMPTZ,
    routes_decayed       INT DEFAULT 0,
    routes_reset         INT DEFAULT 0,
    patterns_found       INT DEFAULT 0,
    candidates_created   INT DEFAULT 0,
    cache_extended       INT DEFAULT 0,
    trigger              TEXT DEFAULT 'scheduled',
    duration_ms          INT
);

ALTER TABLE faq_candidates ADD COLUMN IF NOT EXISTS intent TEXT;
ALTER TABLE faq_candidates ADD COLUMN IF NOT EXISTS feature_class TEXT;
ALTER TABLE faq_candidates ADD COLUMN IF NOT EXISTS representative_query TEXT;
ALTER TABLE faq_candidates ADD COLUMN IF NOT EXISTS best_response TEXT;
ALTER TABLE faq_candidates ADD COLUMN IF NOT EXISTS avg_quality NUMERIC(4,3);
ALTER TABLE faq_candidates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
