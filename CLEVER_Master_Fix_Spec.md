# CLEVER Master Fix Spec

**Status:** implementation spec (not a pitch)  
**Date:** 2026-08-22  
**Code root:** `CLEVER-main/`  
**Companion audit:** `CLEVER_Hardproof_Analysis.md`  
**Audience:** whoever actually ships this — intern, reviewer, or future you  

This file is the contract for making CLEVER *work*. Every defect from the hard-proof audit is here with: what is wrong, why it is fatal or not, the logic of the fix, and the backend change. If a number cannot be measured, we stop printing it. If a control does not block anything, we stop calling it a control.

Do not run `step3_files.py` … `step8_novel.py`. Those generators overwrite source and are how this repo drifted. Quarantine them in Phase 0.

---

## 0. Honest answers (read before writing a line of code)

### 0.1 Are the “novels” actually true?

**No.** Not as research claims. Not as prior-art claims. Not as something you can say to a judge, a VP, Cvent legal, or a patent attorney without getting hurt.

The three-part claim in the handoff was:

> RAS-style pre-LLM filtering + Beta-Bayesian progressive model routing + weekly sleep consolidation — a combination with no known published prior art as of June 2026.

That sentence is false. “Combination with no known prior art” is not a thing you get to say because you stacked three standard techniques and named them after neuroanatomy.

| Branded name | What the code actually is | Prior art (not exhaustive) | Verdict |
|---|---|---|---|
| **RAS Gate** | Regex lookup verbs + SQL field fetch + FAQ full-text + date templates, then return without calling an LLM | Every production chatbot since ~2016; “don’t call the model if a database can answer”; FAQ retrieval; rules engines; semantic routers. The 11M→50 bit RAS story is popular-science (Nørretranders), and the RAS is a brainstem *arousal* network, not a sensory bitrate filter. | **Not novel.** It is a good *product* idea with a misleading name. Keep the behavior. Drop the neuroscience-as-proof. Call it **pre-LLM short-circuit** internally if you want to stay honest. |
| **Myelination / Beta-Bayesian progressive routing** | Per-route Beta(α,β) success rate; cheap model allowed when n≥30 and Wald LCB ≥ τ | Conjugate Beta-Bernoulli is 1930s–1950s textbook. Thompson sampling (1933). Multi-armed bandits in ads for decades. **FrugalGPT** (Chen, Zaharia, Zou, Stanford, 2023, arXiv:2305.05176): cheap→expensive LLM *cascade*, up to 98% cost reduction on their tasks. **RouteLLM** (LMSYS, 2024): weak vs strong routing, 35–85% cost reduction depending on bench. Cascades and routers are a crowded field through 2025–2026. | **The math object is real. The branding is not a discovery.** Using Beta as a per-intent success tracker is a legitimate engineering choice. Claiming “no prior art” next to FrugalGPT (2023) is how you lose a room that has read a paper. |
| **Sleep consolidation** | Weekly cron: delete unused semantic-cache rows, bump a TTL column, reset routes with high Sonnet share, attempt to insert FAQs from logs | Cache eviction, TTL extension, log mining, and “promote frequent queries to canned answers” are SRE / search-ops. Synaptic homeostasis (Tononi & Cirelli) is a *metaphor*. Auto-publishing answers with no human review is a known footgun, not a breakthrough. | **Not novel. Current code also does not do what it says** (it never touches Redis, the cache that actually serves hits). |

**What *is* fair to say, after it actually works:**

> CLEVER is an application-layer gateway that short-circuits lookups and FAQs, projects context, caches exact repeats behind a data version, and routes remaining calls cheap→strong using a per-route success posterior. The pieces are known. The value is whether they fit Cvent Collections traffic.

**What you must stop saying immediately (even before code changes):**

- “no known published prior art as of June 2026”
- “novel research claim” in any deck that a scientist, lawyer, or judge will see
- 85.1% / 93.9% as measured savings
- “human confirmation required” as a safety control
- “BM25” until the ranker is BM25
- “the system gets cheaper every Sunday automatically” until sleep mutates the live cache with tests

If this goes in front of Cvent CAI, security, or finance with the old claims intact, that is the fatal path. The code being intern/Glean-generated is forgivable. The metrics being tautologies presented as measurements is not.

### 0.2 If I had to use this, would it be effective?

**This repo, today: no.** I would not put a single Cvent invoice, contact, or real user query through it. I would not quote its dashboard to finance. I would not trust Stakes Gate to stop a remit. A fake-up here is not an academic oops — it is a wrong budget number and a missing control on money-adjacent intents.

**The architecture, rebuilt to this spec: yes, with a bounded claim.**

A gateway in front of an LLM is the right shape for Collections:

1. A large fraction of “AI” questions in AR are lookups (“balance on 4021”), policy FAQs, and repeats. Those should cost $0.
2. Dumping a whole aging workbook into a prompt is waste. Projecting four fields is real savings *if and only if* the caller currently sends the workbook.
3. Exact cache behind `aging_version` is correct. Stale AR data is worse than a cache miss.
4. Cheap→strong cascade is empirically useful (FrugalGPT, RouteLLM). Expected savings are **task-dependent**, not 80–95% by default.
5. A per-route success posterior (Beta or Wilson) is a reasonable way to *not* send a new intent to the cheap model until it has earned it — *if* the success bit is “cheap model accepted by a real quality check,” not “we forced Sonnet and counted it as a win.”

**What I would expect after a real eval, not what I would print in a slide:**

| Lever | When it pays | Honest range | When it does nothing |
|---|---|---|---|
| Pre-LLM short-circuit (RAS) | Lookups, FAQ, dates, arithmetic | **100% of those queries.** As a share of *all* traffic: maybe 10–40% on a collections helpdesk, **unknown until you measure their mix** | If almost every call is “draft this dunning email” |
| Exact cache | Identical question + same data version + same context | 5–25% on bursty dashboards; near 0% on unique emails | If every query has a different account payload and you hash the payload (which you must, or you leak answers across accounts) |
| Context projection | Caller sends fat documents | 40–80% *token* reduction on fat prompts is plausible | If the app already sends four fields, reduction is ~0% and today’s 85.1% is a lie |
| Cheap→strong cascade | Tasks where a small model is often “good enough” (short classification, simple draft) | Literature: tens of percent of *remaining* LLM spend, sometimes more | Creative/legal/dispute writing; your quality heuristic will either over-escalate (no savings) or under-escalate (wrong emails) |
| Myelination | Same as cascade, with memory across days | Prevents burning a new intent on the cheap model too early | If you train it on the wrong success bit (current code), it unlocks Haiku because Sonnet “succeeded” |
| Sleep | Only as *ops*: expire dead keys, queue FAQ *candidates* | Modest | Auto-FAQ without review will eventually serve a wrong answer at $0 with high confidence |

**Combined 80–95% of Cvent-wide LLM spend:** I would not bet my name on that. That number is what you get when RAS+$0 + a fake 8200-token baseline + Haiku list price are multiplied together. On a real mix dominated by generation, I would budget **30–60% of gateway-attributable spend** as a success, and treat anything above that as a measured surprise.

**Would I use the neuroscience names internally?** Only as mnemonics, and only if every engineer can explain the actual algorithm in one sentence without myelin. I would never use them in a paper, a patent, or a finance review.

**Would I use VpT as currently specified?** No. `$0.50 per account reviewed` is not an outcome. It is a made-up scalar. Finance will ask for the source. There isn’t one. Keep the *formula* (value / tokens) but the value must come from a Collections owner, or you label it `assumed_value_usd` and never “revenue.”

### 0.3 What “fixed” means (definition of done)

The system is fixed when all of these are true at once:

1. A request can be answered by a **real model** (not a canned `[MOCK]` string) through a provider interface.
2. Every dollar on the dashboard is either **provider-reported tokens × a price table** or **$0 because no model was called**. No `8200` constant.
3. Mutating intents cannot complete without a **one-time confirm token**. Prefixing a warning is not enough.
4. Cache cannot return Account A’s answer to Account B.
5. Every path (RAS, cache hit, miss, escalate, stakes) writes a complete `request_log` row with the **classified** intent.
6. `pytest` covers the gates, the cache key, accounting identities, and myelination update rules. CI can run without AWS.
7. `/v1/route`, `/v1/stats`, `/v1/admin/*` require auth. Compose does not publish Postgres/Redis with `clever:clever` as the production posture.
8. README / dashboard / handoff **do not** contain 85.1%, 93.9%, BM25-if-not-BM25, or “no prior art.”

If we ship without (2) and (3), we have polished the demo. We have not fixed it.

---

## 1. Provider strategy — what to use instead of Bedrock

Bedrock is the right *Cvent production* destination (CAI, IAM, data staying in AWS). It is the wrong *study* destination: access is not self-serve, the 5-line swap is unsafe, and you cannot iterate.

### 1.1 Decision

Introduce a **provider interface**. Swap implementations with env, not with comments.

| Provider | Role | When to use |
|---|---|---|
| **`spacexai`** (xAI API, OpenAI-compatible) | **Default for study and for proving the pipeline** | You can get a key today at [console.x.ai](https://console.x.ai). No Cvent CAI ticket. Real tokens in, real tokens out, real bills. |
| **`ollama`** | Offline / zero-spend study | Laptop has no key, or you want to test the gateway without sending collections text to a third party. |
| **`bedrock`** | Cvent production later | Only after CAI approves. Same interface, different client. |
| **`mock`** | Unit tests only | Deterministic fixtures. Never the default when `CLEVER_ENV=dev` if a key exists. `/health` must report `provider=mock` so nobody confuses it with live. |

SpaceXAI is the provider *name*; the actual API is xAI:

- Key: `XAI_API_KEY` (git-ignored `.env` only)
- Base URL: `https://api.x.ai/v1`
- Docs: https://docs.x.ai/developers/quickstart
- Client: `openai` Python SDK with `base_url` **or** `xai-sdk`. Prefer `AsyncOpenAI` so we do not block the event loop (the current Bedrock snippet uses sync `boto3` inside `async def` — that is one of the bugs).

**Live model list (docs.x.ai, fetched 2026-08-22).** Prices per 1M tokens, prompts &lt; 200k:

| Slot | Model id | Input | Output | Why |
|---|---|---|---|---|
| Strong (`MODEL_STRONG`) | `grok-4.6` | $2.00 | $6.00 | Current flagship |
| Cheap (`MODEL_CHEAP`) | `grok-4.3` | $1.25 | $2.50 | Same family, lower price; enough spread to *exercise* cascade |
| Optional cheaper | `grok-build-0.1` | $1.00 | $2.00 | If 4.3 quality is too close to 4.6 on your gold set, try this as cheap |

This spread is **not** Haiku vs Sonnet (~4× on input). Do not expect 93% savings from routing alone on xAI. That is good: it forces savings to come from short-circuit, cache, and real compression — the parts that are actually yours.

**Embeddings:** xAI’s public model card (as of this fetch) is chat/image/video/voice, not Titan-style embeddings. Do **not** block semantic cache on Bedrock Titan. For study, embed **locally**:

- `sentence-transformers` model `all-MiniLM-L6-v2` (384-d)
- Change `semantic_cache.embedding` from `vector(1024)` to `vector(384)`
- Same vectors for write and query; no API key; no data leaves the box

If Cvent later mandates Titan, add `embedders/bedrock_titan.py` and a dimension setting. Do not hardcode 1024 in three files again.

### 1.2 Backend: provider module

**New files**

```
gateway/providers/base.py          # Protocol + Completion dataclass
gateway/providers/spacexai.py      # AsyncOpenAI, api.x.ai
gateway/providers/ollama.py        # httpx to localhost:11434
gateway/providers/bedrock.py       # real async, or keep mock in providers/mock.py
gateway/providers/mock.py          # tests only
gateway/providers/factory.py       # settings.LLM_PROVIDER -> instance
gateway/embedders/local_sbert.py
gateway/embedders/base.py
```

**`Completion` (the only shape cascade/accounting may see)**

```python
@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int          # MUST come from provider usage, never from compressor estimates
    tokens_out: int
    model_id: str
    latency_ms: int
    raw_cost_usd: float | None  # optional; else accounting applies price table
```

**`spacexai.py` rules**

- One shared `AsyncOpenAI` client on app lifespan, not per request.
- `chat.completions.create` (stable usage fields). Timeout `LLM_TIMEOUT_S=30`. `max_tokens` from config.
- Retry: 2 retries on 429/5xx with jitter. Then fail the request; do not silently mock.
- Never swallow errors into a canned “pipeline working” string.
- Map usage: `resp.usage.prompt_tokens` / `completion_tokens`. If usage is missing, **fail closed** for accounting (log error, do not invent random ints).

**Health**

```json
{ "status": "ok", "version": "0.3.0", "provider": "spacexai", "model_cheap": "grok-4.3", "model_strong": "grok-4.6", "db": "ok", "redis": "ok" }
```

If provider is mock, `status` may still be `ok` but dashboard must show a red **MOCK** badge. Silent mock is how the last dashboard lied.

**Env (`.env.example`)**

```
LLM_PROVIDER=spacexai
XAI_API_KEY=
MODEL_CHEAP=grok-4.3
MODEL_STRONG=grok-4.6
LLM_TIMEOUT_S=30
EMBEDDER=sbert
SBERT_MODEL=all-MiniLM-L6-v2
```

Bedrock stays a *future* adapter, not the development blocker.

---

## 2. Target architecture (after the fix)

```
Client (X-API-Key)
    │
    ▼
FastAPI  /v1/route
    │
    ├─ request_id
    ├─ classify intent (YAML is source of truth)
    ├─ stakes (YAML) ── mutate & no confirm_token? return pending_confirmation, NO LLM
    ├─ ras short-circuit (structured → BM25 FAQ → templates)
    ├─ exact cache (sha256 of query+intent+version+canonical context)
    ├─ semantic cache (optional, local embeddings, version-scoped)
    ├─ myelination check (LCB / Beta quantile on cheap-model outcomes only)
    ├─ compressor (real tokenizer on real strings; baseline = uncompressed prompt)
    ├─ cascade (cheap → quality → strong); bill BOTH legs
    ├─ accounting (provider tokens × price table)
    ├─ log ALWAYS
    ├─ myelination update ONLY if cheap model was actually tried
    └─ cache store ONLY if quality passed and not mutate
```

Layer numbers L1–L9 can stay in comments. The running order above is the contract. Semantic cache becomes a real step or we delete the table from the story.

---

## 3. Fix catalog

Each item: problem, why it matters, logic, backend, acceptance.

IDs match the audit (B = blocker, H = high, M = medium, L = low) plus a few structural fixes the audit implied.

---

### P0 — Quarantine generators and pin a bootable install

**Problem.** `setup_files.py` and `step*_files.py` rewrite production files. `requirements.txt` has a UTF-8 BOM and does not list `asyncpg`, `redis`, `apscheduler`. The documented install cannot start the app.

**Why.** You cannot fix what you cannot boot. Running a step script mid-fix will silently revert work.

**Fix.**

1. Move generators to `archive/glean_generators/` and add a top-of-file `raise SystemExit("do not run")`.
2. Rewrite `requirements.txt` (no BOM) with pins:

```
fastapi==0.115.5
uvicorn[standard]==0.32.1
pydantic>=2.11.0,<3
pydantic-settings>=2.7.0,<3
python-dotenv==1.0.1
pyyaml>=6.0
httpx==0.28.1
asyncpg>=0.29.0
redis[asyncio]>=5.0.0
apscheduler==3.10.4
openai>=1.59.0
tiktoken>=0.8.0
sentence-transformers>=3.0.0
rank-bm25>=0.2.2
openpyxl==3.1.2
pytest>=8.0.0
pytest-asyncio>=0.24.0
```

3. Config YAML paths: resolve relative to the package root, not `Path("config/intents.yaml")` CWD.

```python
_ROOT = Path(__file__).resolve().parents[2]  # repo root from gateway/layers/foo.py
_INTENTS_PATH = _ROOT / "config" / "intents.yaml"
```

**Accept.** `pip install -r requirements.txt` then `python -c "from gateway.main import app"` succeeds. Running anything in `archive/` does not change `gateway/`.

---

### B1 — Compression and cost numbers are tautologies

**Problem.** `compressor.py` sets `tokens_before = 8200` always, `tokens_after = n_fields * 300 + query_tokens`. Accounting baseline is “always strong model + 8200 + same output tokens.” Mock `tokens_in` copies the compressor estimate. Dashboard prints 85.1% / ~93.9%.

**Why.** This is the fatal fake-up. Finance, judges, and you will believe a number that is algebra.

**Logic.**

- **Actual cost** = provider `tokens_in/out` × price(model). If two models were called, **sum both**.
- **Baseline cost** = tokenizer(uncompressed prompt) as *estimated input* × strong-model input price + actual `tokens_out` × strong-model output price. Document this as `baseline_method=uncompressed_prompt_strong_model`.
- If `context` is empty, uncompressed == compressed. Reduction **0%**. No silent 8200.
- `mode=baseline` must actually send the uncompressed prompt to the strong model so A/B is real, not a formula.

**Backend.**

`gateway/tokens.py`

```python
import tiktoken
_enc = tiktoken.get_encoding("cl100k_base")  # estimate; label it as such

def count_tokens(text: str) -> int:
    return len(_enc.encode(text or ""))
```

`compressor.build_context`:

```python
full_ctx = json.dumps(req.context, sort_keys=True, default=str) if req.context else ""
projected = {k: req.context[k] for k in fields_needed if k in req.context} if req.context else {}
uncompressed_prompt = query + ("\n\nContext:\n" + full_ctx if full_ctx else "")
compressed_prompt   = query + ("\n\nRelevant context:\n" + yaml_block(projected) if projected else "")
tokens_before = count_tokens(uncompressed_prompt)
tokens_after  = count_tokens(compressed_prompt)
# fields_used = keys actually present, not the YAML list of names we wished we had
```

`accounting.build_accounting`:

```python
actual = cost(usage_legs)  # list of {model, in, out}
baseline = cost([{model: STRONG, in: tokens_before, out: total_out}])
saved = max(0, baseline - actual)
# never clamp saved_pct to look pretty; if actual > baseline, show negative
```

Delete `_FULL_CONTEXT_TOKENS` and `_TOKENS_PER_FIELD`.

Price table in config, not scattered:

```yaml
# config/pricing.yaml
grok-4.3: {in: 1.25, out: 2.50}
grok-4.6: {in: 2.00, out: 6.00}
# keep old haiku/sonnet rows only if bedrock adapter is on
```

**Accept.** Unit test: empty context → `reduction_pct == 0`. Unit test: context 4 small fields vs same 4 fields projected → reduction near 0, not 85. Fixture with a 8k-char blob → reduction matches tiktoken, ±1 token. `/v1/stats` cannot show 93.9% on empty-context triage.

---

### B2 — No authentication

**Problem.** `/v1/route`, `/v1/stats`, `/v1/admin/sleep`, `/docs` are open. CORS `*`.

**Why.** The next Excel load turns this into unauthenticated AR data. Stats leak cost and traces.

**Logic.** Two keys. Route and stats: service key. Admin: admin key. Dashboard sends the service key. Docs disabled when `CLEVER_ENV=prod`. CORS explicit origins.

**Backend.**

`gateway/auth.py` — FastAPI dependency:

```python
async def require_api_key(x_api_key: str | None = Header(None), authorization: str | None = Header(None)):
    offered = x_api_key or bearer(authorization)
    if not hmac.compare_digest(offered or "", settings.CLEVER_API_KEY):
        raise HTTPException(401, "unauthorized")
```

- `require_admin_key` for `/v1/admin/*`
- Reject empty keys on startup if `CLEVER_ENV != test`
- CORS: `CORS_ORIGINS=http://localhost:8080,http://127.0.0.1:8080` (dashboard should be *served by* the app, not `file://`)
- Serve dashboard at `GET /` from FastAPI `FileResponse` so CORS is same-origin
- Rate limit: slowapi or a Redis token bucket, `RATE_LIMIT=60/minute/key`

**Accept.** curl without key → 401. Wrong key → 401. Admin with route key → 401. Dashboard works with key stored after a connect prompt.

---

### B3 — Human confirm is a string prefix

**Problem.** Stakes trips, then the pipeline still calls the (mock) LLM, then prepends “Human confirmation required.” `require_fresh` is unused. `campaign_send` never trips. YAML `stakes:` is unused.

**Why.** A collections gateway that *talks like* it blocks remit but does not block is worse than no gate.

**Logic.** YAML is the only policy. Mutate ⇒ no cache, no RAS, no cheap model, and **no completion** until a confirm token is supplied.

**Backend.**

Expand `config/intents.yaml` so every classifier intent exists, including:

```yaml
campaign_send:
  stakes: mutate
  tier: strong
  human_confirm: true
  cache: false
# same for event_publish, registration_cancel, rfp_send, ticket_escalate, remit, email_blast
```

`stakes_gate.classify` reads YAML (`intent.stakes` or `feature_class.stakes` or `req.stakes==mutate`). Delete the hardcoded `_MUTATE_INTENTS` set or keep it only as a test fixture that *must* match YAML (assert on load).

New request field: `confirm_token: Optional[str]`.

On trip without token:

```python
cid = str(uuid.uuid4())
await redis.setex(f"confirm:{cid}", 300, json.dumps({
    "intent": intent, "query_hash": qh, "api_key_hash": ..., "created_at": ...
}))
# log the attempt, gate_fired=stakes, model_used=none, pending=true
return RouteResponse(status="pending_confirmation", confirmation_id=cid,
                     response="This intent is classified as a mutation. Resubmit with confirm_token to proceed.")
# NO provider.complete()
```

On trip with valid token: `GETDEL` (single use), force strong model, cache off, then respond `status=ok`.

On trip with invalid/expired token: 409, do not run.

Default `STAKES_PREVIEW_LLM=false`. If someone later wants a draft preview before confirm, that is a separate explicit flag, still not an action.

**Accept.** `POST /v1/route` `{query:"remit invoice 12", intent_hint:"remit"}` → `pending_confirmation`, zero provider calls (mock spy). Second POST with token → one strong-model call. `campaign_send` keyword trip has the same behavior. Tests read YAML, not a Python set.

---

### B4 — Zero tests

**Problem.** `tests.gitkeep` is empty. No gold set. No way to know a fix did not resurrect 8200.

**Why.** Glean-generated code fails in the seams (wrong regex group, wrong intent column). Tests are the only way this stays honest after the next edit.

**Backend.** `tests/` with pytest-asyncio. No live network in default CI.

Minimum files:

| File | What it locks |
|---|---|
| `test_compressor.py` | empty context 0%; tiktoken identity; projects only YAML fields |
| `test_accounting.py` | two-leg cascade sums both costs; RAS 100% only when tokens=0 |
| `test_stakes.py` | YAML mutate list; confirm token single-use |
| `test_cache_key.py` | different context → different key; same account+query+version → same key |
| `test_classifier.py` | hint vs keyword vs default; no first-substring traps we care about |
| `test_ras_structured.py` | invoice vs account; INV-2024 not account 2024; empty table miss |
| `test_ras_template.py` | today; days-until uses group of the date |
| `test_ras_faq.py` | BM25 threshold; does not match on answer-only words |
| `test_myelination.py` | forced strong does not increment α; escalate increments β; LCB vs τ |
| `test_logger.py` | classified intent written; cache hit writes a row |
| `test_auth.py` | 401 without key |
| `test_pipeline_gold.py` | gold set JSON → expected `exit_layer` |

Gold set `harness/gold_set.json`:

```json
[
  {"q": "what is today's date", "expect_layer": "ras.template"},
  {"q": "who handles disputes", "expect_layer": "ras.faq", "seed": "faq"},
  {"q": "what is the balance on account 4021", "expect_layer": "ras.structured", "seed": "aging"},
  {"q": "remit payment for 4021", "expect_layer": "stakes.pending"},
  {"q": "draft a dunning email", "expect_layer": "llm", "feature_class": "collections_outreach"}
]
```

**Accept.** `pytest -q` green on a clean checkout with `LLM_PROVIDER=mock`.

---

### B5 — requirements / boot

Covered under P0. Tracked so it cannot be dropped.

---

### B6 — Structured lookup will leak AR data

**Problem.** When `aging_data` is loaded, any unauthenticated client can ask “what is the balance on 4021.” Invoice path is unimplemented. `\b(\d{4,6})\b` matches `2024` inside `INV-2024-089`.

**Logic.** Auth is B2. Resolver must still be correct and least-privilege: return only the asked field, never `raw` JSONB. Invoice regex **before** account digits. Account match must not be inside an `INV-` token.

**Backend.** `structured_lookup.py`:

```python
# 1. invoices first
inv = re.search(r"\bINV-[\d-]+\b", query, re.I)
# 2. account ids that are not inside INV-...
acct = re.search(r"(?<!INV-)(?<![A-Z])\b(\d{5,8})\b", query)  # tighten: 5-8 digits, skip years
```

`structured_resolver.py`: implement `entity_type in {account, invoice}`. Invoice query:

```sql
SELECT account, balance, days_overdue, status, contact, invoice_ids
FROM aging_data
WHERE $1 = ANY(invoice_ids)
  AND aging_version = (SELECT active_aging_version FROM active_pointer LIMIT 1)
LIMIT 1
```

Add `harness/load_aging.py` that reads xlsx, writes `data_versions` + `aging_data` + updates `active_pointer`. Refuse to load if `CLEVER_API_KEY` is default/empty and `CLEVER_ENV=prod`.

Never log full row at INFO. Do not put PII in `decision_trace` (entity id hashed or truncated).

**Accept.** Test: query `status of INV-2024-089` hits invoice, not account 2024. Test: empty table → miss, no exception. Loader dry-run prints row count without committing if `--dry-run`.

---

### H1 — Cache key omits context

**Problem.** Key is `{query, feature_class, intent_hint, aging_version}`. Two accounts, same question → same HIT.

**Fix.** Canonicalize the **projected** context (the fields that intent needs) plus `aging_version` plus classified intent plus normalized query. Hash **SHA-256**.

```python
payload = {
  "q": req.query.strip().lower(),
  "intent": classified_intent,
  "fc": req.feature_class,
  "ver": aging_version,
  "ctx": projected_or_empty,  # sorted JSON
}
key = "exact:" + ver + ":" + sha256(json.dumps(payload, sort_keys=True))
```

**Accept.** Same query, context `{account:1}` vs `{account:2}` → miss. Same query+account+version → hit.

---

### H2 — Cache HIT accounting and logging

**Problem.** HIT returns the first call’s `cost_usd`. Trace says `~$0`. No `request_log` row. Sleep cannot see cache efficacy. Dashboard under-counts.

**Fix.** Store in Redis:

```json
{
  "response": "...",
  "baseline_cost_usd": 0.027,
  "original_cost_usd": 0.0017,
  "original_model": "grok-4.3"
}
```

On HIT, response accounting:

```
tokens_in=0, tokens_out=0, cost_usd=0,
baseline_cost_usd=<stored baseline>,
saved_usd=baseline, saved_pct=100,
cache_hit=true
```

Always `write_request_log(..., model_used="cache", gate_fired=null, cache_hit=true)`.

**Accept.** Two identical calls: second row in DB has `cost_usd=0`, `model_used=cache`. Stats `total_cost` does not double-count the miss.

---

### H3 — Logger writes `intent_hint` not classified intent

**Problem.** `req.intent_hint or "unknown"` → stats bucket everything as `unknown`. `query_hash` column never written. `quality_score` never written. RAS `gate_fired` collides with stakes trips.

**Fix.** `write_request_log` takes an explicit `LogRecord` dataclass: `intent`, `query_hash`, `route_class`, `cache_hit`, `ras_gate`, `stakes_reason`, `quality_score`, `vpt`, `request_id`, `usage_legs` JSONB.

Schema additions (`db/schema_v03.sql` as a real migration, not another `ALTER` dump in the same file without a version):

```sql
ALTER TABLE request_log
  ADD COLUMN IF NOT EXISTS request_id UUID,
  ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS query_text_redacted TEXT,
  ADD COLUMN IF NOT EXISTS usage_legs JSONB,
  ADD COLUMN IF NOT EXISTS query_hash TEXT;  -- already exists; START WRITING IT
```

`query_hash = sha256(normalized_query + intent + version)`.

Stats: stakes trips = `stakes_reason IS NOT NULL`. RAS = `ras_gate_fired IS NOT NULL`. Do not reuse one column.

**Accept.** Keyword-classified triage without hint logs `intent=triage`. Dashboard stakes panel does not show FAQ hits.

---

### H4 — Myelination success signal is wrong; critical reset is dead; demo lies

**Problem.** `success = not escalated` ⇒ forced strong (cold start / stakes) increments α. Critical requires `not escalated and score<0.7`, which cannot happen after a pass at τ≥0.90. Demo sets n=55, prints Cerebellar and `cheap_ok`. Wald LCB goes negative at the prior. Two different floors (0.90 vs 0.92). Fire-and-forget task.

**Logic.** Myelination measures **“is the cheap model good enough on this route?”** Therefore:

| Event | Update |
|---|---|
| Cheap tried, quality passed, not escalated | α += 1, n += 1 |
| Cheap tried, quality failed, escalated | β += `w_wrong` (3), n += 1 |
| Strong forced (stakes or cold start) | **no update** |
| Human thumbs-down on a cheap answer (new endpoint) | severity=critical → reset or β += large |
| Provider error | no update |

Phase labels are cosmetic. Eligibility is: `n_obs >= N_MIN` AND `lcb >= tau`. Print phase from n, never the other way around.

**LCB:** stop using Wald. Use the Beta quantile:

```python
from math import ... 
# scipy optional: 
from statistics import # or implement Acklam inverse
lcb = beta_ppf(0.05, alpha, beta)   # 5th percentile of posterior
```

If we want zero new deps, implement a Wilson interval on `p = (α-1)/(α+β-2)` for the Beta(1,1) prior — but Beta quantile is the thing the comments already claim. Add `scipy` *or* a 20-line inverse-incomplete-beta. Do not ship LCB &lt; 0.

**Tau:** one table. Quality floor and myelination τ come from `features.yaml` `q_floor`. Delete `_TAU` duplicate.

**Update call:** `await myelination.update(...)` **in-request** (not `create_task`) unless it exceeds 20ms; then use the same pool connection. Lost-update is already handled by `alpha = alpha + 1` in SQL — keep that, just don’t drop the await.

**Demo script:** if n=55, print `Myelinating` and compute LCB in Python before printing eligibility. Delete “30 consecutive successes.”

**Accept.** Test: 30 forced-strong calls → α,β still at prior, still ineligible. Test: 30 cheap passes with α starting 1,1 → n=30, LCB computed, eligibility iff LCB≥τ. Test: critical endpoint resets. Demo script stdout does not contain `Cerebellar` for n=55.

---

### H5 — Mutate-like intents not gated

Covered by B3 YAML expansion. Explicit accept: keyword `launch campaign` → `campaign_send` → pending_confirmation.

Also: classifier first-substring is policy. Reorder / use word boundaries. `"report"` as a keyword is too broad — change to phrases (`"give me a summary"`, `"weekly report"`). Add tests for near-misses.

`intent_hint`: treat as hint. Confidence 1.0 only if hint ∈ YAML **and** (keyword agrees OR caller role is `trusted_service`). Otherwise keyword/default. Prevents unauthenticated hint=`triage` from masking a remit phrase — actually: if *either* hint or keyword says mutate, mutate wins (fail closed).

---

### H6 — Sleep FAQ promote is broken and dangerous

**Problem.** Groups on `query_hash` (never written). Then fetches the global hottest `semantic_cache` row (empty, unwired). If “fixed” naively, auto-inserts answers into the $0 path. Prunes `semantic_cache` not Redis. `LIKE '%sonnet%'` treats stakes-forced strong as “this route is bad.”

**Logic.** Sleep is **ops with a review queue**, not unsupervised learning.

**Backend.**

Phases:

1. **Prune exact cache:** Redis keys `exact:*` whose `hits==0` and age &gt; 7d. This requires storing metadata: use a HASH per key `exactmeta:{k}` with `hits, created_at` or a Postgres `exact_cache_meta` table. Pick Postgres meta — easier to query in sleep.
2. **Strengthen:** keys with hits ≥ 10 → `EXPIRE` 2h (or config).
3. **Validate myelination:** escalation rate = cheap_tried AND escalated, **excluding** `stakes_forced` and `cold_start`. If rate &gt; 0.30 and n≥10, reset that route.
4. **FAQ candidates:** frequent `query_hash` with stable response → `INSERT INTO faq_candidates (...)`. **Do not** insert into `faq_entries`.
5. **VpT daily:** keep, once vpt is actually logged.

New admin (admin key):

- `GET /v1/admin/faq/candidates`
- `POST /v1/admin/faq/candidates/{id}/approve`
- `POST /v1/admin/sleep` remains, but returns **job id** and runs under a Redis `SET sleep_lock NX EX 3600` so two workers don’t double-run.

APScheduler: call the async function directly (`AsyncIOScheduler`), not `lambda: create_task`. Document: **one Uvicorn worker** for v0.3, or run sleep as a separate `python -m gateway.sleep`. Multi-worker without lock is a bug.

**Accept.** Integration test with fakeredis/postgres: sleep does not write `faq_entries`. Approve endpoint does. Forced-sonnet routes are not reset.

---

### H7 — Open Redis / Postgres defaults

**Problem.** Compose publishes `5432` and `6379`, password `clever`, Redis no AUTH.

**Fix.** `infra/docker-compose.yml`:

```yaml
postgres:
  environment:
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-clever}
  ports:
    - "${POSTGRES_PUBLISH:-127.0.0.1:5432:5432}"
redis:
  command: ["redis-server", "--requirepass", "${REDIS_PASSWORD:-clever}"]
  ports:
    - "${REDIS_PUBLISH:-127.0.0.1:6379:6379}"
```

App DSN and `REDIS_URL=redis://:password@localhost:6379/0`. `.env.example` documents this. `CLEVER_ENV=prod` refuses to start if password is `clever` or API key is empty.

**Accept.** `config.py` startup check covered by a unit test on a `Settings` validator.

---

### H8 — Dashboard XSS, CORS *, missing panels

**Problem.** `innerHTML` with `feature_class` / `intent` / `reason`. `GleanBridge` throws. VpT, myelination, TCR returned by API but not rendered. Stakes panel shows RAS.

**Fix.**

- `escapeHtml()` on every interpolated value, or build DOM with `textContent`.
- Serve dashboard from FastAPI (B2).
- API key field.
- Render `vpt_by_intent`, `myelination`, `tail_cost`.
- Trips panel uses `stakes_reason`. Separate “short-circuit” feed for RAS.
- Remove GleanBridge or wrap in `if (window.GleanBridge)`.
- Badge: if health.provider==mock → **MOCK DATA**.

**Accept.** Feature class `<img onerror=alert(1)>` does not execute. Manual check of panels.

---

### H9 — Cascade drops cheap-leg cost

**Problem.** On escalate, only strong usage is kept. Real money disappears from the ledger.

**Fix.** `cascade.run` returns `legs: list[Completion]`. Accounting sums all legs. Telemetry stores `usage_legs`. Trace shows both.

**Accept.** Test: cheap fail + strong success → `cost_usd == cost(cheap)+cost(strong)` &gt; cost(strong).

---

### H10 — `[MOCK]` in default text forces perpetual escalate

**Problem.** Quality’s `mock_signal` deducts 0.3. Default mock string contains `[MOCK]`. Default intents always escalate. Then myelination sees failure. Loop.

**Fix.** Delete `mock_signal` from production quality. Mock provider is tests-only. Quality checks (keep):

1. Refusal regex (keep, tune).
2. Length floor (keep).
3. **Groundedness (new):** if intent is triage/report, every `$amount` and account id in the output must appear in the **projected context** or RAS would have fired. If context is empty, skip this check (don’t fail everything).
4. Optional `QUALITY_LLM_JUDGE=false` by default (costs money).

Sonnet/strong `accepted_sonnet` score 1.0 is a lie. Store `quality.method=unchecked_strong` and `score=null` so the dashboard does not plot 1.0 quality for unscored answers.

**Accept.** Strong path does not write `quality_score=1.0`. Cheap path never looks for `[mock]`.

---

### M1 — FAQ is not BM25

**Problem.** Postgres `ts_rank` labeled BM25. Threshold 0.01. Rank includes answer text so answer-side words false-hit.

**Fix (pick one; do the first for v0.3):**

**A. Honest small-corpus BM25 (recommended for study).** Load FAQ rows into memory (there will be tens, not millions). `rank_bm25.BM25Okapi` over **question** tokens. Threshold calibrated on a 20-pair labeled set in `harness/faq_labels.json`. Start at 0.4+ relative score; do not use 0.01.

**B. Keep Postgres FTS** but rename every log/trace/dashboard string from BM25 to `fts`. Raise threshold. Rank `question` only. GIN index on `to_tsvector('english', question)`.

Do **not** claim BM25 if you pick B.

**Accept.** A query that only appears in an answer does not HIT. Labeled pairs: precision on the fixture ≥ 0.8.

---

### M2 / M3 — Invoice resolver and dead `_days_from_now`

Invoice: B6. Template: `m.group(3)` is the date for `how (far|many days) (until|to|from) (DATE)`. Add a unit test that `how many days until 2026-12-31` returns a number, not None.

Arithmetic: if we promise “templates do arithmetic,” add an explicit resolver with `ast` on a numeric-only grammar — or remove arithmetic from the talking points. Do not `eval`.

---

### M4 — YAML surface area vs claims

Write the real intents and feature classes into YAML until YAML ⊇ classifier map. If we don’t support venue sourcing yet, **delete it from the classifier** instead of pretending 14 classes exist. Features.yaml must include every `feature_class` the API accepts; unknown class → 422.

---

### M5 — Sleep vs Redis

Covered in H6.

---

### M6 — Stats mixes RAS and stakes

Covered in H3.

---

### M7 — Demo script

Covered in H4.

---

### M8 — VpT is fiction and RAS drops it

**Logic.** Keep the metric, change the contract.

- YAML field rename: `assumed_value_usd` (not “business outcome”).
- Header comment: “not Cvent finance-approved.”
- Always attach vpt to accounting, including RAS and cache (tokens=0 → **vpt is undefined, store NULL**, do not divide by 1).
- `alert_rules` either wire into stats or delete.

**Accept.** RAS row: `vpt IS NULL`, `cost_usd=0`. LLM row: vpt uses actual token sum including cascade legs.

---

### M9 — Generators overwrite source

Covered in P0.

---

### M10 — CWD-relative YAML

Covered in P0.

---

### M11 — No indexes on `request_log`

```sql
CREATE INDEX IF NOT EXISTS request_log_ts_idx ON request_log (ts DESC);
CREATE INDEX IF NOT EXISTS request_log_intent_ts_idx ON request_log (intent, ts DESC);
CREATE INDEX IF NOT EXISTS request_log_stakes_idx ON request_log (ts DESC) WHERE stakes_reason IS NOT NULL;
```

Stats summary: default window 24h, not all-time full table scan. All-time remains an explicit `?window=all`.

---

### M12 — In-process weekly cron

Covered in H6 (lock + single worker or separate process).

---

### L1–L7 — Nits, still fix

| ID | Fix |
|---|---|
| L1 | `datetime.now(timezone.utc)` |
| L2 | Save `requirements.txt`, `.gitignore`, `.env.example` as UTF-8 no BOM |
| L3 | Leave empty `__init__.py` (needed for package) |
| L4 | Drop unused `httpx` **only if** ollama/spacexai don’t need it; spacexai uses openai SDK; keep httpx for ollama |
| L5 | Guard GleanBridge |
| L6 | Health: `db: "error"` without exception string to clients; full error in server logs |
| L7 | Re-save `schema.sql` as UTF-8; replace `�12` with `section 12` |

---

### Additional structural fixes (not in the original ID list, required anyway)

**S1. Pipeline exception handling.** `route()` has no try/except. Pool failure → unhandled 500. Catch, log `request_id`, return 503 with a stable code. Never return stack traces.

**S2. Request size.** Pydantic: `query` max 8k chars, `context` JSON max 256KB. 413 over that.

**S3. `mode=baseline`.** Must skip RAS, cache, compression, myelination; call strong model on uncompressed prompt; still log. This is how you *measure* savings vs yourself, not vs a constant.

**S4. Semantic cache (optional v0.3, required v0.4).** After exact miss, embed compressed query+intent with SBERT, cosine vs `semantic_cache` where `aging_version` matches, threshold 0.92 (config). On HIT treat like exact for accounting ($0) but trace `cache.semantic`. On store, insert embedding. If we skip v0.3, say “unwired” in health and **remove it from the pitch**.

**S5. Quality vs features.yaml `q_floor: 1.0` on reconciliation.** That means cheap never passes. Fine if stakes already forced strong; still don’t leave a floor that is impossible for other classes.

**S6. OpenAPI.** `/docs` off in prod. In dev, still behind API key if possible (custom middleware).

**S7. Kill the 5-line Bedrock snippet** from the handoff. Replace with “implement `providers/bedrock.py` against this Protocol, async, timeouts, usage from the response.”

**S8. Handoff / talking points / dashboard copy.** Strip disallowed claims (section 7 below). Version bump to `0.3.0-dev`.

---

## 4. Implementation phases (order matters)

Do not start with dashboard chrome. The first honest number requires B1 + a real provider.

### Phase 0 — Make it bootable and stop the bleeding (½ day)

- P0 generators quarantined, requirements fixed, paths fixed, BOM gone
- Auth keys in `.env` (B2 minimal: one header)
- Health reports `provider`
- Claim purge in README/handoff/dashboard strings (85.1, 93.9, prior art, BM25-if-lying)

### Phase 1 — Honest pipeline core (2–3 days)

- Provider interface + `spacexai` + `mock`
- Tokenizer compressor (B1)
- Accounting sums legs (H9)
- Logger classified intent + query_hash + cache hits (H3, H2)
- Cache key includes context (H1)
- Stakes YAML + confirm token (B3, H5)
- Template group fix (M3)
- Structured invoice + INV- vs year (B6 without Excel yet)
- Myelination update rules (H4)
- pytest from B4 for everything above

**Exit:** mock-provider tests green; with `XAI_API_KEY`, one real `POST /v1/route` shows provider usage in the trace that matches the xAI response.

### Phase 2 — RAS made true + data (1–2 days)

- BM25 FAQ or renamed FTS (M1)
- Aging loader + seed FAQ (B6)
- Gold set including live DB
- VpT NULL on zero tokens (M8)

### Phase 3 — Ops and sleep (1 day)

- Redis password, bind localhost (H7)
- Sleep lock, Redis prune, FAQ *candidates* (H6)
- Indexes + 24h stats window (M11)
- Admin approve FAQ

### Phase 4 — Surface (1 day)

- Dashboard XSS + panels + mock badge (H8)
- Serve UI from FastAPI
- Semantic cache with SBERT (S4) or explicitly “off”
- `mode=baseline` live comparison (S3)

### Phase 5 — Study protocol (1 day)

- Run gold set twice: `mode=clever` vs `mode=baseline` against **xAI**
- Export a table: n, layer mix, actual USD, baseline USD, saved_pct **measured**
- That table is the only savings claim you are allowed to use

Do not parallelize Phase 1. Later phases can overlap 3 and 4.

---

## 5. Study protocol (how we prove it without Bedrock)

1. Get `XAI_API_KEY`. Small credit load. You will spend cents, not hundreds, if the gold set is ~50 prompts.
2. Load **synthetic** aging (faker accounts), not the real `Aging 05.18.26.xlsx`, until auth + bind + `.gitignore` are in place.
3. Run:

```text
pytest -q
python -m harness.run_gold --mode clever
python -m harness.run_gold --mode baseline
python -m harness.report   # writes harness/last_run.md
```

4. Report columns: query, expect_layer, actual_layer, tokens_in, tokens_out, cost_usd, baseline_cost_usd, model, cache_hit, ras_gate, stakes.
5. **Pass criteria for “this works”:**

- 100% of gold `expect_layer` match (or documented diffs)
- `cost_usd == 0` iff no provider call
- `saved_pct` on empty-context generation is small (routing only), not 93%
- mutate gold cases never call cheap model and never complete without confirm
- no cross-account cache HIT in the adversarial pair

If Phase 5 numbers are ugly, we publish the ugly numbers. We do not retune `_FULL_CONTEXT_TOKENS`.

---

## 6. What you may say after the fix vs what you may not

**Allowed (if Phase 5 measured it):**

- “On this N-query gold set, clever mode cost $X vs baseline $Y (Z% less). Breakdown: A% short-circuit, B% cache, C% cheaper model, D% fewer prompt tokens.”
- “Lookups and FAQs do not call a model.”
- “Mutating intents require a confirm token and always use the strong model.”
- “Per-route cheap-model eligibility uses a Beta posterior lower bound. Cold start uses the strong model.”
- “Weekly job expires cold cache keys and queues FAQ candidates for approval.”

**Forbidden:**

- no known prior art / novel combination / first to combine RAS+Beta+sleep
- 85.1% / 93.9% / 80–95% Cvent-wide unless Phase 5 on *production* traffic says so
- BM25, unless `rank_bm25` or equivalent is on the path
- human-in-the-loop, unless confirm_token is required
- self-improving every Sunday, unless candidates auto-apply (they must not)
- VpT as recovered cash

---

## 7. File-level change map (so implementation does not wander)

| File | Action |
|---|---|
| `requirements.txt` | rewrite, no BOM, complete pins |
| `gateway/config.py` | keys, provider, models, timeouts, refuse default secrets in prod |
| `gateway/models.py` | `confirm_token`, `status`, `confirmation_id`, `request_id`, tighter types |
| `gateway/main.py` | auth deps, CORS, serve dashboard, health.provider, admin FAQ, sleep job id |
| `gateway/auth.py` | **new** |
| `gateway/tokens.py` | **new** |
| `gateway/pipeline.py` | order, confirm branch, await myelin, log all exits, no 8200 |
| `gateway/providers/*` | Protocol + spacexai + mock; bedrock later |
| `gateway/layers/classifier.py` | YAML-driven, mutate fail-closed, phrase keywords |
| `gateway/layers/stakes_gate.py` | YAML only |
| `gateway/layers/ras/*` | invoice first, BM25/FTS, template group 3 |
| `gateway/layers/cache.py` | sha256 + context; HIT $0 + log |
| `gateway/layers/compressor.py` | real prompts, real counts |
| `gateway/layers/cascade.py` | legs[] |
| `gateway/layers/quality.py` | drop mock_signal; groundedness; null score for strong |
| `gateway/layers/myelination.py` | cheap-only updates; Beta quantile; one τ |
| `gateway/telemetry/*` | LogRecord; vpt NULL at 0 tokens; TCR on 24h |
| `gateway/sleep/consolidation.py` | Redis+meta, candidates, lock |
| `config/*.yaml` | full intent/feature/pricing tables; assumed_value_usd |
| `db/schema_v03.sql` | columns + indexes + faq_candidates + vector(384) |
| `infra/docker-compose.yml` | passwords, bind localhost |
| `harness/*` | load_aging, gold_set, run_gold, report |
| `tests/*` | as B4 |
| `superblocks/clever_dashboard.html` | escape, panels, key, mock badge |
| `demo/trigger_demyelination.py` | honest prints |
| `archive/glean_generators/` | move step scripts |
| `CLEVER_Project_Handoff_for_LLMs.md` | rewrite claims or stamp SUPERSEDED |

---

## 8. Risks if we “just fix it quickly”

| Temptation | Outcome |
|---|---|
| Keep 8200 as “fallback when context empty” | Recreates the 85% slide |
| Count forced Sonnet as myelination success “to warm the prior” | Unlocks cheap model with no evidence |
| Auto-approve FAQ because the review UI is extra work | Silent wrong $0 answers |
| Use file:// dashboard + CORS `*` “just for the demo” | XSS + key theft later |
| Load the real aging xlsx to impress a judge | Data incident |
| Say “inspired by RAS / myelin / sleep” in a *paper* | Reviewer cites FrugalGPT page 1 |
| One giant commit that “fixes everything” | You will not be able to see which fix broke logging |

Fix in the phase order. After each phase, tests must be green.

---

## 9. Direct answers, compressed

**Alternative to Bedrock for the study:** SpaceXAI / xAI (`XAI_API_KEY`, `https://api.x.ai/v1`, cheap `grok-4.3`, strong `grok-4.6`). Local SBERT for embeddings. Ollama if you cannot send text off-box. Keep Bedrock as a later adapter for Cvent CAI — do not block on it.

**Are the novels true?** No. Pre-LLM short-circuit, cheap→strong cascade, Beta success tracking, and cache hygiene are **standard**. FrugalGPT (2023) and RouteLLM (2024) already occupy this design space. The names are branding. The “no prior art” line is the most dangerous sentence in the handoff. Delete it.

**Would I use this?** Not the current repo. After this spec is implemented and Phase 5 is measured, **yes as an internal cost gateway** for lookup-heavy Collections traffic, with savings claims limited to the measured table. I would not use it as a safety system beyond “mutate requires confirm + strong model,” and I would not use VpT dollars until Collections leadership owns the YAML.

**What kills you:** reprinting 93.9%; loading real AR data into an open port; telling a room the science is new.

---

*Next step is implementation of Phase 0 + Phase 1 against this spec, not another architecture essay. If you want that built in this repo, say to execute the spec starting at Phase 0.*
