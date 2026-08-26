# CLEVER — Complete Project Handoff (for any AI assistant)

> **SUPERSEDED (2026-08-22).** Do not use the savings numbers, novelty claims, or Bedrock-swap snippet in this file. Current contract: `CLEVER_Master_Fix_Spec.md`. Current runtime: `CLEVER-main/` v0.3.0 (mock provider, generic cheap/strong tiers). Independent audit: `CLEVER_Hardproof_Analysis.md`.


**Purpose of this document:** Give any LLM (Claude, ChatGPT, Gemini, Copilot, etc.) the full context to continue building, testing, or debugging CLEVER. Read this top to bottom before touching code.

**Author:** Shwetank Pandey — Intern, Collections (Finance), Cvent
**Repo:** https://github.com/Shwetank-Pandey_cvent/CLEVER
**Local path:** `C:\CLEVER` (Windows)
**Current version:** v0.2.0 — all core + novel layers built, running on a MOCK LLM provider.

---

## 1. What CLEVER is (the one-paragraph pitch)

CLEVER is an **AI cost-optimization gateway** that sits BETWEEN a Cvent application and a Large Language Model (LLM). Instead of optimizing inside the model, it filters, classifies, compresses, caches, and routes every request BEFORE a single token reaches the LLM. The novel claim: RAS-style pre-LLM filtering + Beta-Bayesian progressive model routing + weekly "sleep consolidation" self-maintenance — a combination with no known published prior art as of June 2026.

**The analogy:** The whole car is built — conveyor belt, payments, dryers, soap. Bedrock (real AI) is the water. Everything works today except real model responses, which are currently mocked.

---

## 2. Tech stack

| Layer | Tech | Status |
|---|---|---|
| Gateway app | Python 3.14 (spec pinned 3.12, we run 3.14 locally), FastAPI, Uvicorn, async | ✅ working |
| Data models | Pydantic v2, pydantic-settings | ✅ |
| Relational DB + vector store | Postgres 16 + pgvector (Docker) | ✅ running |
| Cache / KV | Redis 7 (Docker) | ✅ running |
| Container runtime | Rancher Desktop (dockerd/moby engine) — NOT Docker Desktop | ✅ |
| Scheduler | APScheduler (Sleep Consolidation, Sunday 3am) | ✅ |
| LLM provider | AWS Bedrock (Claude 3.5 Haiku + Sonnet, Titan Embed v2) | ❌ MOCKED — access pending |
| Dashboard | Standalone HTML (polls /v1/stats) | ✅ working |
| Excel loading | openpyxl / pandas | ⚠️ not wired yet |

---

## 3. Repository structure

```
C:\CLEVER\
├── gateway/
│   ├── main.py                 # FastAPI app, lifespan pools, /health /v1/route /v1/stats /v1/admin/sleep
│   ├── config.py               # pydantic-settings, reads .env
│   ├── models.py               # RouteRequest, RouteResponse, AccountingResult, QualityResult
│   ├── pipeline.py             # THE 15-step orchestrator — heart of the system
│   ├── providers/
│   │   └── bedrock.py          # MOCK provider — 5-line swap to real Bedrock pending
│   ├── layers/
│   │   ├── classifier.py       # L1 — intent detection (config → keyword → default)
│   │   ├── stakes_gate.py      # L2 — blocks mutations (remit, blast, reconciliation)
│   │   ├── ras_gate.py         # L7 — orchestrates 3 pre-LLM checks
│   │   ├── ras/
│   │   │   ├── structured_lookup.py    # RAS check 1 — detect direct DB lookups
│   │   │   ├── structured_resolver.py  # RAS check 1 — run the Postgres query
│   │   │   ├── faq_match.py             # RAS check 2 — BM25 full-text FAQ match
│   │   │   └── template_resolver.py     # RAS check 3 — regex/date/template
│   │   ├── cache.py            # L4 — exact cache (Redis, version-scoped keys)
│   │   ├── myelination.py      # L8 — Beta-Bayesian progressive routing
│   │   ├── compressor.py       # L3 — strips context to only needed fields
│   │   ├── cascade.py          # L5 — Haiku → quality gate → Sonnet escalation
│   │   └── quality.py          # L5b — pure-Python quality scorer
│   ├── telemetry/
│   │   ├── accounting.py       # cost + savings math, build_ras_accounting
│   │   ├── vpt.py              # Value-per-Token attribution
│   │   ├── tail_cost.py        # Tail Cost Ratio (TCR) detector
│   │   └── logger.py           # writes every call to request_log
│   └── sleep/
│       └── consolidation.py    # L9 — weekly prune/strengthen/validate/promote
├── config/
│   ├── intents.yaml            # 25+ intents → stakes + tier + fields
│   ├── features.yaml           # 14 feature classes → quality floor + cache policy
│   └── vpt_outcomes.yaml       # intent → business $ value per outcome
├── db/
│   ├── schema.sql              # core tables
│   └── schema_novel.sql        # aging_data, faq_entries, vpt_daily + ALTER request_log
├── demo/
│   └── trigger_demyelination.py  # live demo: reset a route to Cortical
├── superblocks/
│   └── clever_dashboard.html   # live dashboard (open in Chrome)
├── infra/
│   └── docker-compose.yml      # postgres + redis
├── docs/
│   └── CLEVER_Judge_Talking_Points.md
├── requirements.txt
├── .env                        # local secrets — GIT IGNORED
├── .env.example                # template
└── step3_files.py ... step8_novel.py   # setup scripts that generated the code
```

---

## 4. The 15-step pipeline (gateway/pipeline.py)

Order matters. Each request flows through these in sequence; the first layer that can answer returns early.

1. **Classifier** — detect intent (config lookup → keyword scan → feature-class default)
2. **Stakes Gate** — if mutation (remit/blast/reconciliation/explicit mutate flag) → SUSPEND optimization, force Sonnet, cache OFF, require human confirm
3. **RAS Gate** — 3 free checks (only on non-mutation reads):
   - structured lookup ($0, <5ms) — direct Postgres field answer
   - BM25 FAQ match ($0, <10ms)
   - template/regex ($0, <1ms) — dates, arithmetic
4. **Exact Cache** — Redis, version-scoped key `exact:{aging_version}:{md5}`; HIT returns ~$0
5. (Semantic cache — table exists, not yet wired)
6. **Myelination Check** — Beta(alpha,beta) registry per route_class; decides if cheap model is eligible via Lower Confidence Bound (LCB) vs quality floor (tau)
7. **Router** — picks Haiku (cheap) or forces Sonnet (stakes tripped OR myelination not eligible)
8. **Compressor** — projects context to only the fields the intent needs (8200 → ~1220 tokens, 85% reduction)
9. **Cascade** — call chosen model; if Haiku fails quality floor → escalate to Sonnet
10. **VpT** — Value-per-Token = business outcome $ ÷ tokens × 1000
11. **Tail-Cost** — computed on /v1/stats, not per-request
12. **Accounting** — actual cost vs baseline (baseline = full context + Sonnet + no cache)
13. **Telemetry** — write full row to request_log (Postgres)
14. **Myelination Update** — async; success bumps alpha, failure bumps beta, critical failure resets to Cortical
15. **Cache Store** — save response to Redis for future exact hits

---

## 5. The 5 novel layers (explain these to judges)

**RAS Gate (L7)** — brain's Reticular Activating System filters 11M bits/sec → 50 bits. CLEVER filters 50-85% of queries before any LLM call using structured lookup + BM25 FAQ + templates. All $0.

**Myelination Engine (L8)** — frequently-used neural paths get myelin (100x faster, cheaper). CLEVER tracks per-route success with Beta-Bayesian stats. Phases: Cortical (new, <30 obs, always strong model) → Myelinating (30-100 obs) → Cerebellar (100+ obs, cheap model unlocked IF LCB ≥ quality floor). Bad response → de-myelination (partial or full reset).

**VpT Attribution (L5)** — Value-per-Token. Converts "we saved X% tokens" into "$Y business value per 1000 tokens." Wins finance judges.

**Tail-Cost Detector (L5.5)** — TCR = cost of top 10% priciest calls ÷ bottom 90%. TCR > 1.0 means the expensive minority costs more than everything else. Governance metric.

**Sleep Consolidation (L9)** — Sunday 3am job: prune zero-hit cache, strengthen hot entries (extend TTL), de-myelinate routes with >30% escalation, promote frequent patterns to FAQ. System gets cheaper/smarter weekly, automatically.

---

## 6. Database schema (8 tables)

- `data_versions` — aging file version tracking
- `active_pointer` — single-row pointer to the active aging version
- `request_log` — every API call, full JSONB trace + cost + vpt + route_class
- `semantic_cache` — pgvector(1024) embeddings, HNSW index (not yet wired)
- `myelination_registry` — route_class PK, alpha, beta, n_obs, phase logic
- `aging_data` — real Excel data (⚠️ currently EMPTY — needs loading)
- `faq_entries` — BM25 knowledge base (seeded with 5 manual entries)
- `vpt_daily` — daily VpT aggregates (populated by Sleep Consolidation)

---

## 7. What WORKS today (verified in testing)

- ✅ Full 15-step pipeline runs end to end
- ✅ Classifier: config/keyword/default all fire correctly
- ✅ Stakes Gate: trips on remit, email_blast, campaign_send, reconciliation, explicit mutate flag
- ✅ RAS template: "what is today's date" → $0, ~8-11ms
- ✅ RAS FAQ: "who handles disputes" → BM25 score 0.395, HIT, $0
- ✅ RAS structured lookup: gracefully MISSES when aging_data empty (no crash)
- ✅ Exact cache: same query twice → HIT, ~37ms, ~$0
- ✅ Compressor: 8200 → 1220 tokens, 85.1% reduction
- ✅ Cascade: Haiku → quality fail → Sonnet escalation
- ✅ Myelination: all 3 phases (Cortical/Myelinating/Cerebellar) + LCB gate + de-myelination demo
- ✅ VpT: computes per intent with correct outcome values
- ✅ DB logging: every call written to request_log
- ✅ Dashboard: live, auto-refresh every 5s, shows KPIs/donut/trips/feed
- ✅ /v1/stats: summary, model_breakdown, vpt_by_intent, myelination, tail_cost

**Key measured numbers:**
- Compression: 8,200 → 1,220 tokens (85.1%)
- Cost savings (compressed + routed): up to 93.9%
- RAS-resolved calls: 100% savings (never reach LLM)
- Cerebellar unlock requires ~alpha=95, beta=5 so LCB(0.907) ≥ tau(0.90)

---

## 8. What is MISSING / TODO

1. **Real Bedrock provider** — BIGGEST GAP. Currently returns hardcoded `[MOCK]` string with fake token counts. Access request in progress (must go through Cvent CAI team via #cvent-ai-development Slack channel — NOT self-serve). 5-line swap ready in `gateway/providers/bedrock.py`.
2. **Aging data loading** — `aging_data` table is empty. Need a `harness/load_aging.py` to load the real Excel file (Aging 05.18.26, ~161 invoices / 70 accounts) into Postgres. This makes RAS structured lookup fire live.
3. **Semantic cache** — table + pgvector index exist, but not wired into pipeline (needs Titan embeddings = needs Bedrock).
4. **GO/NO-GO test harness** — automated script to run all test cases and produce token-reduction + quality pass/fail numbers.
5. **Real quality scoring** — quality.py works but the `mock_signal` check is a testing artifact that disappears with real Bedrock.

---

## 9. Setup — what to download & install (Windows)

### Prerequisites
```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e   # spec pins 3.12; 3.14 also works locally
winget install --id Microsoft.VisualStudioCode -e
# Container runtime: install Rancher Desktop (set engine to dockerd/moby), NOT Docker Desktop
```

### Cvent network note (IMPORTANT)
Cvent's corporate proxy does TLS inspection. pip fails with SSL errors unless configured. Create `%APPDATA%\pip\pip.ini` (ASCII, NO BOM):
```
[global]
trusted-host =
    pypi.org
    files.pythonhosted.org
prefer-binary = true
```
`prefer-binary = true` avoids source builds that need Rust/MSVC (which fail behind the proxy).

### Python environment
```powershell
cd C:\CLEVER
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### requirements.txt contents
```
fastapi==0.115.5
uvicorn[standard]==0.32.1
pydantic>=2.11.0
pydantic-settings>=2.7.0
python-dotenv==1.0.1
pyyaml>=6.0
httpx==0.28.1
asyncpg>=0.29.0
redis[asyncio]>=5.0.0
apscheduler==3.10.4
openpyxl==3.1.2
# boto3   ← add when Bedrock access confirmed
```

### .env file (copy from .env.example, never commit)
```
CLEVER_ENV=dev
LOG_LEVEL=info
POSTGRES_DSN=postgresql://clever:clever@localhost:5432/clever
REDIS_URL=redis://localhost:6379/0
AWS_REGION=us-east-1
AWS_PROFILE=clever-dev
BEDROCK_MODEL_HAIKU=anthropic.claude-3-5-haiku-20241022-v1:0
BEDROCK_MODEL_SONNET=anthropic.claude-3-5-sonnet-20241022-v2:0
BEDROCK_MODEL_EMBED=amazon.titan-embed-text-v2:0
```

---

## 10. Start-of-day routine (get it running)

```powershell
cd C:\CLEVER
.\.venv\Scripts\Activate.ps1
docker compose -f infra\docker-compose.yml up -d          # start Postgres + Redis

# First time only — apply schema:
docker cp db\schema.sql clever_postgres:/schema.sql
docker exec -it clever_postgres psql -U clever -d clever -f /schema.sql
docker cp db\schema_novel.sql clever_postgres:/schema_novel.sql
docker exec -it clever_postgres psql -U clever -d clever -f /schema_novel.sql

# Seed the FAQ (first time only):
docker exec -it clever_postgres psql -U clever -d clever -c "INSERT INTO faq_entries (question, answer, source) VALUES ('what is the collections SLA','Standard collections SLA is 30 days from invoice due date. Escalation at 60 days.','manual'),('who handles disputes','Disputes are handled by the AR team. Submit via the dispute intent with supporting docs.','manual') ON CONFLICT (question) DO NOTHING;"

# Start the gateway:
python -m uvicorn gateway.main:app --reload --port 8080
```

Then open:
- `http://localhost:8080/docs` — Swagger UI (run all tests here via POST /v1/route → Edit Value box)
- `http://localhost:8080/health` — liveness
- `http://localhost:8080/v1/stats` — dashboard data
- `superblocks/clever_dashboard.html` — open in Chrome for the live dashboard

**Testing tip:** In Swagger, always use the "Edit Value" box — never copy the curl command (it can insert `{{` double braces and break JSON).

---

## 11. The 5-line Bedrock swap (do this when access lands)

In `gateway/providers/bedrock.py`, replace the mock `invoke()` body with:
```python
async def invoke(model_id, messages, context_tokens):
    import boto3, json
    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    body = json.dumps({"anthropic_version": "bedrock-2023-05-31",
                       "max_tokens": 1024, "messages": messages})
    resp = client.invoke_model(modelId=model_id, body=body)
    data = json.loads(resp["body"].read())
    return {
        "text": data["content"][0]["text"],
        "usage": {"tokens_in": data["usage"]["input_tokens"],
                  "tokens_out": data["usage"]["output_tokens"],
                  "model_id": model_id}
    }
```
Then `pip install boto3`, `aws sso login --profile clever-dev`, restart. Nothing else changes — the pipeline is provider-agnostic.

---

## 12. THE GOAL

**Immediate goal (hackathon):** A live demo where a judge sends real queries and watches CLEVER filter, compress, route, and cache them — showing real token savings, real Stakes Gate trips, real myelination learning, and real VpT dollar attribution.

**The novel research claim (3 parts):**
1. RAS-style pre-LLM filtering at the application-model boundary
2. Beta-Bayesian progressive model routing with automatic de-myelination
3. Sleep Consolidation as a self-maintaining AI gateway

**Business goal for Cvent:** Cut LLM spend 80-95% across Finance/Collections and the wider Cvent product surface (events, registration, marketing, venue sourcing, support, analytics) while enforcing hard safety controls on money-moving operations — and prove the dollar value per token, not just token counts.

---

## 13. Known gotchas (save the next LLM time)

- Windows PowerShell `Out-File -Encoding utf8` adds a BOM that breaks pip.ini — use ASCII via `[System.IO.File]::WriteAllText(..., ASCII)`.
- Setup scripts (`stepN_files.py`) must be manually created in VS Code and saved before running — they don't auto-create from chat.
- Files written by Python must use `encoding="utf-8"` or em-dashes crash on cp1252.
- Empty dict `{}` is falsy in Python — caused the compressor baseline bug (fixed: baseline is always 8200 when intent has defined fields).
- Cache intercepts before myelination — flush Redis (`docker exec -it clever_redis redis-cli FLUSHDB`) before testing myelination phases.
- Myelination "cheap_ineligible" at p_hat=0.88 is CORRECT behavior — LCB (0.82) < floor (0.90). Need ~alpha=95, beta=5 for LCB ≥ 0.90.
- Bedrock is NOT self-serve at Cvent — must go through the CAI team (#cvent-ai-development). AIDE/Cloud-Infra will redirect you there.

---

*End of handoff. Repo: https://github.com/Shwetank-Pandey_cvent/CLEVER — CLEVER v0.2.0, all core + novel layers built on mock provider, awaiting Bedrock access.*
