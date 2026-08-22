-- v0.4: cheap_n for explore counting; semantic cache 384-d + isolation columns.

ALTER TABLE myelination_registry
    ADD COLUMN IF NOT EXISTS cheap_n INT DEFAULT 0;

DROP INDEX IF EXISTS semantic_cache_embedding_idx;

ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS intent TEXT;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS context_hash TEXT;
ALTER TABLE semantic_cache ADD COLUMN IF NOT EXISTS baseline_cost_usd NUMERIC(12,6);

-- Recreate embedding column at 384 dims (local MiniLM). Empty table expected.
DO $$
BEGIN
    BEGIN
        ALTER TABLE semantic_cache DROP COLUMN IF EXISTS embedding;
        ALTER TABLE semantic_cache ADD COLUMN embedding vector(384);
    EXCEPTION WHEN others THEN
        RAISE NOTICE 'semantic embedding alter skipped';
    END;
END $$;

CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx
    ON semantic_cache
    USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS semantic_cache_iso_idx
    ON semantic_cache (feature_class, aging_version, context_hash, intent);
