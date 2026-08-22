raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
One-time setup: writes docker-compose.yml and schema.sql to disk.
Run from C:\CLEVER with: python setup_files.py
"""
import os

os.makedirs("infra/cdk", exist_ok=True)
os.makedirs("db/migrations", exist_ok=True)

# â”€â”€ docker-compose.yml â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
docker_compose = """\
version: "3.9"

services:

  postgres:
    image: pgvector/pgvector:pg16
    container_name: clever_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: clever
      POSTGRES_PASSWORD: clever
      POSTGRES_DB: clever
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U clever -d clever"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    container_name: clever_redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  postgres_data:
  redis_data:
"""

# â”€â”€ db/schema.sql â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
schema = """\
-- CLEVER Database Schema (Â§12 of CLEVER_Build_Handoff_v3.1)

CREATE EXTENSION IF NOT EXISTS vector;

-- Every aging file upload gets a new row here
CREATE TABLE IF NOT EXISTS data_versions (
    version     TEXT PRIMARY KEY,
    status      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Single-row pointer: which version is currently active
CREATE TABLE IF NOT EXISTS active_pointer (
    id                   BOOL PRIMARY KEY DEFAULT true CHECK (id),
    active_aging_version TEXT REFERENCES data_versions(version)
);

-- Every API call is recorded here with full JSONB trace
CREATE TABLE IF NOT EXISTS request_log (
    id                BIGSERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ DEFAULT now(),
    mode              TEXT,
    feature_class     TEXT,
    intent            TEXT,
    stakes            TEXT,
    gate_fired        TEXT,
    model_used        TEXT,
    tokens_in         INT,
    tokens_out        INT,
    cost_usd          NUMERIC(12,6),
    baseline_cost_usd NUMERIC(12,6),
    quality_score     NUMERIC(4,3),
    latency_ms        INT,
    decision_trace    JSONB,
    query_hash        TEXT,
    aging_version     TEXT,
    degraded          TEXT
);

-- Stores embeddings for similar-query lookup
CREATE TABLE IF NOT EXISTS semantic_cache (
    id            BIGSERIAL PRIMARY KEY,
    embedding     vector(1024),
    query_text    TEXT,
    response      TEXT,
    feature_class TEXT,
    aging_version TEXT,
    hit_count     INT DEFAULT 0,
    created_at    TIMESTAMPTZ DEFAULT now(),
    last_hit_at   TIMESTAMPTZ,
    ttl_seconds   INT
);

CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx
    ON semantic_cache
    USING hnsw (embedding vector_cosine_ops);

-- Beta-Bayesian per-route learning registry
CREATE TABLE IF NOT EXISTS myelination_registry (
    route_class     TEXT PRIMARY KEY,
    alpha           INT DEFAULT 1,
    beta            INT DEFAULT 1,
    n_obs           INT DEFAULT 0,
    current_tier    TEXT,
    last_correction TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT now()
);
"""

with open("infra/docker-compose.yml", "w", newline="\n") as f:
    f.write(docker_compose)

with open("db/schema.sql", "w", newline="\n") as f:
    f.write(schema)

# Verify
print("Files created:")
print(f"  infra/docker-compose.yml  exists={os.path.exists('infra/docker-compose.yml')}")
print(f"  db/schema.sql             exists={os.path.exists('db/schema.sql')}")

