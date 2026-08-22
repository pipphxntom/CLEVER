# CLEVER Hard-Proof Analysis

**Document type:** Independent implementation audit (not a pitch review)  
**Auditor role:** Research / staff-engineer review of code, schema, configs, ops, and security  
**Code root:** `CLEVER-main/`  
**Handoff read:** `CLEVER_Project_Handoff_for_LLMs.md` (v0.2.0)  
**Date:** 2026-08-21  
**Method:** Every runtime Python file, YAML config, SQL schema, compose file, dashboard, and the handoff were read. Math was recomputed independently. Syntax of runtime Python was parsed. Imports were attempted against the local interpreter. **No claim was accepted because the handoff or a comment said it was true.**

**Legend**

| Mark | Meaning |
|---|---|
| `[PASS]` | Present, wired, and does what the handoff/code comment says |
| `[PARTIAL]` | Present, but incomplete, incorrect, or only true under demo conditions |
| `[FAIL]` | Missing, dead, false, or actively misleading |
| `[BLOCKER]` | Would stop a real Cvent deployment or makes a reported number unusable |

This is a laptop hackathon skeleton with a working request path and a mocked LLM. It is not an enterprise AI gateway. Several “verified” numbers are algebraic identities of hardcoded constants, not measurements.

---

## 0. Verdict (read this first)

**CLEVER is a FastAPI demo pipeline that can classify, short-circuit a few toy queries, fake a compression ratio, call a mock model, and write rows to Postgres.** The conveyor belt exists. The water is not connected. The savings dashboard is largely a function of constants (`8200`, `300 tokens/field`, Haiku vs Sonnet list prices), not of real tokens or real models.

**Do not take the following to a judge, a VP, or a security review as proven:**

- 85.1% token reduction
- up to 93.9% cost savings
- 50–85% of queries filtered pre-LLM
- “human confirmation required” as a control
- BM25 FAQ matching
- weekly self-maintenance that makes the system cheaper
- enterprise readiness
- “5-line swap” to production Bedrock

**What is actually true:** a 15-named-step orchestrator runs; RAS/cache/myelination/cascade functions exist; Postgres+Redis are specified in compose; the LLM is mocked; aging data is empty; there are **zero tests**; there is **no authentication**.

**Enterprise deploy decision: NO-GO.** Not close.

---

## 1. What this system actually is

A single-process FastAPI app (`gateway/main.py`) exposing:

| Endpoint | Auth | What it really does |
|---|---|---|
| `POST /v1/route` | none | Runs the pipeline |
| `GET /health` | none | `SELECT 1` + Redis ping |
| `GET /v1/stats` | none | Full-table aggregates over `request_log` |
| `POST /v1/admin/sleep` | none | Fire-and-forget weekly job |
| `/docs` | none | OpenAPI |

There is no Cvent application integration. The caller is whoever can hit port 8080. Context is whatever JSON the caller sends. The “LLM” is `gateway/providers/bedrock.py`, which sleeps 50 ms and returns canned strings plus `random.randint(120, 280)` output tokens.

That last point poisons every cost, savings, VpT, cascade, myelination, and dashboard number that depends on token counts or model quality.

---

## 2. Master scorecard

### 2.1 Handoff “what WORKS today”

| Handoff claim | Result | Evidence |
|---|---|---|
| Full 15-step pipeline runs end to end | `[PARTIAL]` | Steps 5 and 11 are absent per request. Pipeline exists and is callable. LLM is mock. |
| Classifier: config / keyword / default all fire | `[PASS]` | `classifier.py` implements that order. Precision is poor (see §4.1). |
| Stakes Gate trips on remit, email_blast, campaign_send, reconciliation, explicit mutate | `[FAIL]` | `campaign_send` is **not** in the mutate set. YAML `stakes:` is **not read**. Only `remit`, `email_blast`, feature classes `{reconciliation, ledger, payment}`, and `stakes=="mutate"`. |
| RAS template: “what is today’s date” → $0 | `[PASS]` | Regex in `template_resolver.py` matches. This is a date format, not AI. |
| RAS FAQ: “who handles disputes” BM25 HIT | `[PARTIAL]` | Postgres `ts_rank` can hit if FAQ is seeded. It is **not BM25**. Threshold `0.01` is extremely permissive. |
| RAS structured lookup misses cleanly when `aging_data` empty | `[PASS]` | Count-then-return-None. Invoice path never implemented even when data exists. |
| Exact cache: second call HIT ~$0 | `[FAIL]` | HIT is real (Redis). Accounting returned is the **first call’s cost**, not $0. HIT is **not written** to `request_log`. Key ignores most of `context`. |
| Compressor 8200 → 1220, 85.1% | `[BLOCKER]` | Tautology: `8200` and `4 * 300 + ~20`. Independent recomputation reproduces 85.1% with **no document and no tokenizer**. |
| Cascade: Haiku fail → Sonnet | `[PARTIAL]` | Code path exists. Mock default text contains `[MOCK]`, so default intents always “fail” and escalate. Escalation cost of the failed Haiku call is dropped. |
| Myelination 3 phases + LCB + de-myelin demo | `[PARTIAL]` | Beta math is real. Demo script labels Myelinating `n_obs=55` as Cerebellar and claims `cheap_ok` when LCB is 0.83 < 0.90. Critical reset from the pipeline is **dead code**. |
| VpT per intent with correct outcome values | `[PARTIAL]` | Formula runs. Values are made-up YAML dollars. RAS path computes VpT then **discards** it. Tokens of 0 become a divisor of 1, which would inflate VpT if it were logged. |
| DB logging of every call | `[FAIL]` | Cache hits are not logged. Logged `intent` is `intent_hint` or `"unknown"`, not the classified intent. `query_hash` is never written. |
| Dashboard live, 5s refresh, KPIs / donut / trips / feed | `[PARTIAL]` | HTML polls `/v1/stats`. XSS via unsanitized `innerHTML`. Stakes-trip panel also shows RAS hits (`gate_fired IS NOT NULL`). VpT / myelination / TCR from the API are **not rendered**. |
| `/v1/stats` summary, model_breakdown, vpt, myelination, tail_cost | `[PARTIAL]` | Endpoints return those keys. Queries are unindexed full-table scans. Intent column is wrong (see logger). |

### 2.2 Handoff “key measured numbers”

| Number | Result | Proof |
|---|---|---|
| Compression 8,200 → 1,220 (85.1%) | `[BLOCKER]` | `tokens_before = 8_200` always. `tokens_after = len(fields) * 300 + query_tokens`. Triage has 4 fields → 1220. `(1 - 1220/8200)*100 = 85.122%`. |
| Cost savings up to 93.9% | `[BLOCKER]` | Same constants + Haiku $0.80/$4 vs Sonnet $3/$15, using the mock’s fake `tokens_in`. Recomputed ~93.8% at 180 output tokens. |
| RAS-resolved calls: 100% savings | `[PARTIAL]` | `build_ras_accounting` **hardcodes** `saved_pct = 100.0`. True only in the sense that no mock call happened. Not a measured LLM saving. |
| Cerebellar unlock ~α=95, β=5, LCB 0.907 ≥ τ 0.90 | `[PASS]` | Recomputed: p̂=0.9500, σ=0.0217, LCB=0.9075. This is the one myelination number that is arithmetically correct. |

### 2.3 Handoff tech-stack table

| Layer | Claimed | Result |
|---|---|---|
| Gateway Python 3.14 / spec 3.12, FastAPI, uvicorn, async | `[PARTIAL]` | FastAPI app is real. This machine parsed the code under **Python 3.13.2**. Spec/handoff/runtime disagree. |
| Pydantic v2 + pydantic-settings | `[PASS]` | Used. `RouteRequest` has almost no validation (any `feature_class`, unbounded `query`). |
| Postgres 16 + pgvector | `[PARTIAL]` | Compose image is `pgvector/pgvector:pg16`. pgvector index exists. Semantic cache is unwired. Default password `clever`. Port 5432 published to host. |
| Redis 7 | `[PARTIAL]` | Compose is real. **No password.** Port 6379 published. `redis` Python package is **not** in `requirements.txt`. |
| Rancher Desktop | n/a | Environment claim, not in repo. |
| APScheduler Sunday 03:00 | `[PARTIAL]` | Job is registered. `apscheduler` **missing from requirements.txt**. In-process cron will double-fire under multiple uvicorn workers. Job does not maintain the cache that is actually used (Redis). |
| AWS Bedrock Haiku / Sonnet / Titan | `[FAIL]` | Mock only. Titan never called. Swap snippet is not production-safe (sync boto3 in `async def`, no timeout/retry, no inference-profile IDs). |
| Dashboard | `[PARTIAL]` | Standalone HTML. Not Superblocks despite the folder name. |
| Excel loading | `[FAIL]` | Handoff already says not wired. Confirmed: `harness/` is an empty gitkeep. No loader. |

### 2.4 Config vs claimed surface area

| Claim | In repo | Result |
|---|---|---|
| 25+ intents in `intents.yaml` | **8** (`triage`, `email_draft`, `inbox_check`, `email_blast`, `remit`, `notes`, `dispute`) | `[FAIL]` |
| 14 feature classes in `features.yaml` | **3** (`collections_outreach`, `reconciliation`, `customer_facing`) | `[FAIL]` |
| Classifier keyword map ~22 intents | Yes, in Python, not YAML | `[PARTIAL]` — two sources of truth, YAML unused for stakes/tier |
| FAQ seeded with 5 manual entries | Handoff seed SQL inserts **2** | `[FAIL]` |
| Semantic cache table exists, not wired | True | `[PASS]` as a gap statement |
| GO/NO-GO harness | Missing. Zero `test_*.py`. `tests.gitkeep` is empty | `[FAIL]` |

---

## 3. Pipeline hard-proof (the 15 steps)

Order in `gateway/pipeline.py` is: Classifier → Stakes → RAS → Exact cache → (skip semantic) → Myelination → Router → Compressor → Cascade → VpT → (skip tail-cost) → Accounting → Telemetry → Myelination update → Cache store.

| Step | Name | Result | Notes |
|---|---|---|---|
| 1 | Classifier | `[PARTIAL]` | Works. First substring wins. Caller `intent_hint` is trusted at confidence 1.0 with **no auth**. |
| 2 | Stakes Gate | `[FAIL]` | Does not match handoff’s trip list. `require_human_confirm` does not confirm anything. `require_fresh` is never read. YAML `stakes:` ignored. |
| 3 | RAS Gate | `[PARTIAL]` | Three checks run. Structured lookup cannot resolve invoices. FAQ is `ts_rank`, not BM25. One of four template resolvers is dead. |
| 4 | Exact cache | `[PARTIAL]` | Redis GET/SET with TTL 3600. Key omits context body. HIT skips telemetry. |
| 5 | Semantic cache | `[FAIL]` | Not in the pipeline. Table only. |
| 6 | Myelination check | `[PARTIAL]` | Beta-Bernoulli + Wald LCB is implemented. Forced-Sonnet successes train the cheap path as if they were Haiku successes. |
| 7 | Router | `[PARTIAL]` | Binary Haiku/Sonnet. No real routing policy beyond stakes + LCB. |
| 8 | Compressor | `[BLOCKER]` | Field projection of caller-supplied JSON is real. Token counts are invented. Baseline is always 8200 even for an empty context. |
| 9 | Cascade | `[PARTIAL]` | Mock quality is a string heuristic. Sonnet is never scored. Double-call cost not accounted. |
| 10 | VpT | `[PARTIAL]` | Arithmetic only. Outcome $ are guesses. Not attributed to an actual business event. |
| 11 | Tail-cost | `[PARTIAL]` | Computed on `/v1/stats`, not per request (handoff admits this). `NTILE(10)` is meaningless at demo volume. Dashboard does not show it. |
| 12 | Accounting | `[BLOCKER]` | Baseline = “always Sonnet + 8200 tokens + same fake output tokens”. Savings is defined into existence. |
| 13 | Telemetry | `[FAIL]` | Wrong intent field. Cache hits omitted. `query_hash` unused. RAS `gate_fired` collides with stakes trips. |
| 14 | Myelination update | `[FAIL]` | Fire-and-forget `asyncio.create_task`. Success = `not escalated`, so **forced Sonnet counts as success**. Critical reset cannot fire. Lost updates under concurrency. |
| 15 | Cache store | `[PARTIAL]` | Stores response + original accounting. Mutations skipped (good). Stores even low-quality / escalated answers (bad). |

---

## 4. Layer-by-layer (brutal)

### 4.1 Classifier (`gateway/layers/classifier.py`)

**What is real:** Three-stage fallback. YAML load. Keyword map. Feature-class defaults.

**What is wrong:**

- This is not an NLU classifier. It is `if kw in query.lower()`.
- First match wins, so map order is policy. Broad tokens (`"report"`, `"segment"`, `"analyse"`) will steal traffic.
- `intent_hint` is a backdoor: any caller can force `remit` or `triage` at confidence 1.0.
- YAML is loaded then barely used (existence check for hints). Stakes, tier, `human_confirm` in YAML do not drive behavior.
- Many keyword intents have **no** `intents.yaml` fields, so the compressor later reports ~99% reduction on query-only prompts against an 8200-token baseline.

### 4.2 Stakes Gate (`gateway/layers/stakes_gate.py`)

Handoff: trips on remit, email_blast, **campaign_send**, reconciliation, explicit mutate.

Code:

```python
_HIGH_STAKES_CLASSES = {"reconciliation", "ledger", "payment"}
_MUTATE_INTENTS = {"remit", "email_blast"}
```

`campaign_send`, `event_publish`, `registration_cancel`, `rfp_send`, `ticket_escalate` classify as those intents and then **proceed into optimization** (cache, Haiku eligibility, compression).

`require_human_confirm=True` only causes `pipeline.py` to **prefix a warning string** onto the mock response after the model has already been invoked:

```text
STAKES_GATE_TRIP — optimization suspended.
Human confirmation required before any action fires.
```

There is no confirm token, no two-phase commit, no outbox, no action channel. The gate does not stop a money movement because **this process never moves money**. If a future engineer wires `remit` to a payment API and trusts this prefix, that is a production incident.

`require_fresh` is set and never consulted.

**Collections-relevant conclusion:** this is a demo tripwire, not a control.

### 4.3 RAS Gate — scientific and engineering

**Neuroscience, since the pitch uses it:** the reticular activating system is a brainstem arousal network (wakefulness), not a 11×10⁶ → 50 bit/s sensory filter. That bit-rate story is popular-science (Nørretranders), not a measured RAS transfer function. Naming a regex+SQL+FAQ cascade “RAS” is metaphor. It is not a mechanism.

**Check 1 — structured lookup**

- `[PARTIAL]` Regex for 4–6 digit “accounts” and `INV-…`.
- Lookup verbs include `"what is"`, `"get"`, `"show me"` — high false-candidate rate.
- `\b(\d{4,6})\b` matches the `2024` inside `INV-2024-089`, so invoices are preferentially misread as accounts.
- Resolver implements **account only**. `entity_type == "invoice"` always returns `None`.
- `pool` is passed into `attempt()` and unused.
- When `aging_data` is populated, this path returns **account balances and contacts with no authentication**. That is a data-exposure bug waiting on the Excel load, not a future feature.

**Check 2 — “BM25 FAQ”**

Postgres `ts_rank(to_tsvector(...), plainto_tsquery(...))` is **not BM25**. BM25 has `k1`, `b`, and document-length normalization. `ts_rank` is a different ranking function (term coverage / TF-style).

`_BM25_THRESHOLD = 0.01` will accept very weak overlaps. Ranking is over `question || ' ' || answer`, so answer-side words can trigger a HIT and return a canned answer to the wrong question.

Hit-count updates are not transactional with the read in a meaningful way; acceptable for a demo, not for a knowledge base.

**Check 3 — templates**

| Resolver | Result |
|---|---|
| Today / current date | `[PASS]` |
| Days between `YYYY-MM-DD` and today | `[PASS]` |
| `how far/many days until DATE` | `[FAIL]` — regex captures the date in **group 3**; handler parses **group 1** (`"far"` / `"many days"`). Always excepts, returns None. Dead code. |
| Format invoice | `[PASS]` — string formatting, not a lookup |

**RAS “filters 50–85% of queries”:** `[FAIL]` — no measurement, no production query mix, aging table empty, FAQ has ~2 rows if the operator remembered to seed them. The percentage is a target, not a result.

### 4.4 Exact cache (`gateway/layers/cache.py`)

**Real:** `exact:{aging_version}:{md5}` , TTL 1h, degrades on Redis errors.

**Wrong:**

1. Key material is `{query, feature_class, intent_hint}` only. Two different accounts with the same question share a cached answer.
2. MD5 of a small JSON blob is fine as a cache key; version scoping is the right idea.
3. On HIT, pipeline returns stored `accounting` from the **miss** that filled the cache. Trace says `"saved": "~$0"` while `cost_usd` is the original LLM (mock) cost. The handoff’s “HIT ~$0” is the trace string, not the numbers a judge will read off the response.
4. HIT does not call `write_request_log`. Dashboard systematically **under-counts** cache effectiveness.
5. Sleep consolidation never touches Redis, so “prune zero-hit cache” does not apply to the only cache that works.

### 4.5 Compressor — the 85.1% number

```python
_FULL_CONTEXT_TOKENS = 8_200
_TOKENS_PER_FIELD    = 300
tokens_before = _FULL_CONTEXT_TOKENS          # always
tokens_after  = len(fields_needed) * 300 + query_tokens
```

Independent evaluation:

```
fields_needed for triage = 4
query_tokens ≈ max(20, words*1.4) = 20
tokens_after = 1220
reduction = 85.1%
```

No tiktoken, no Bedrock tokenizer, no aging file. If `req.context` is `{}`, the prompt sent to the model is **just the query**, while the system still reports 8200 → 1220.

An earlier generator (`step5_files.py`) used `8200 if req.context else query_tokens`. The handoff “gotcha” says empty dict is falsy so they “fixed” it by **always** using 8200. That is how you lock a demo percentage, not how you measure compression.

Field projection itself (copy only named keys into the prompt) is a real, standard idea. The **percentage is not**.

### 4.6 Quality + cascade

Quality checks: refusal regex, minimum character length, substring `"[mock]"`, optional digit presence. Deduct a few tenths from 1.0. Compare to `q_floor` from YAML (default 0.92).

This is not factuality, not groundedness against `aging_data`, not schema validation, not a judge model.

Consequences in the mock:

- Default mock text contains `[MOCK]` → deduction 0.3 → score 0.7 → fail 0.92 → always escalate.
- `triage` / `email_draft` canned strings are long and numeric → score 1.0 → never escalate.
- Sonnet is **always accepted at score 1.0** (`accepted_sonnet()`), including the same `[MOCK]` string.

On escalate, accounting keeps **only Sonnet usage**. The Haiku attempt is free in the ledger. In production that understates cost every time the cheap model fails.

Forced-Sonnet path (`force_model` set) sets `escalated=False`, which later becomes myelination **success**.

### 4.7 Myelination — is it Beta-Bayesian progressive routing?

**Statistical content that is real:**

- Per-`route_class` Beta(α, β) in Postgres.
- Posterior mean p̂ = α/(α+β).
- Posterior variance of a Beta, σ = sqrt(αβ / ((α+β)² (α+β+1))).
- Wald LCB = p̂ − 1.96σ.
- Cheap path iff `n_obs ≥ 30` and LCB ≥ τ.

That is a conjugate Beta-Bernoulli success tracker with a normal-approximation lower bound. It is a legitimate, textbook method. It is **not** a full Bayesian decision rule (no utility, no Thompson sampling, no proper Beta quantile / inverse incomplete beta). For small n the Wald LCB goes **negative** (prior α=β=1 → LCB ≈ −0.066); they bypass that with the n<30 cold start.

**Engineering content that is wrong:**

| Issue | Proof |
|---|---|
| Success signal is not quality | `success = not result["escalated"]`. Forced Sonnet (Cortical) increments **α**. The cheap model is unlocked by a streak of **expensive** calls. |
| Critical de-myelination cannot fire | `critical` requires `not escalated and score < 0.7`. Non-escalated Haiku already passed q_floor ≥ 0.90. Forced Sonnet score is 1.0. Dead branch. |
| Demo script is false | Sets α=50, β=5, n=55. Prints “Cerebellar” and “cheap_ok”. Phase rule is Cerebellar at **n≥100**. LCB=**0.8338** < τ=0.90 → `cheap_ineligible`. |
| “30 consecutive successes rebuild trust” | False. `n_obs` counts all trials, not consecutive. Failures also increment `n_obs`. |
| τ tables disagree | Myelination `_TAU["collections_outreach"]=0.90`. Quality `features.yaml` `q_floor=0.92`. Two floors. |
| Concurrency | Read-modify-write via SQL `alpha = alpha + 1` is OK in isolation; still no transaction tying cascade result to the update (the update is a detached task). Process crash after response → lost observation. |
| `route_class` | `"{intent}:standard"` if classifier confidence ≥ 0.8 else `high`. Keyword matches are 0.8 → always `standard`. |

**Research-honesty note (not a novelty hunt, a prior-art sanity check):** cascading cheap→expensive models is published (FrugalGPT, 2023; numerous router papers). Beta-Bernoulli bandits for arm selection are 1950s–1990s textbook. Treating “does the cheap model pass a heuristic” as a Bernoulli is an engineering choice, not a new statistical object. The combination as branded is a product story.

### 4.8 VpT

```
VpT = (default_value_usd * outcome_count) / max(tokens, 1) * 1000
```

`default_value_usd` examples: triage $0.50, email_draft $2.00, dispute $5.00. The YAML itself says a finance judge will ask where these come from. They are not from Cvent collections data. `outcome_count` defaults to 1 and is caller-supplied — another unauthenticated lever to inflate the metric.

`alert_rules()` is **never called**.

RAS path: `vpt_calc.compute(...)` result is dropped; `build_ras_accounting` has no vpt fields; logger writes `accounting.get("vpt")` → NULL.

### 4.9 Tail-cost detector

TCR = sum(cost in top NTILE) / sum(rest), on rows with `cost_usd > 0` in a 24h window.

Problems: RAS $0 rows excluded (so the “free” path does not help TCR); cache hits absent; costs are mock; NTILE on n<10 is junk; no alert sink (log line only); UI ignores `tail_cost`.

### 4.10 Sleep consolidation

Handoff: Sunday 03:00 prune zero-hit cache, strengthen hot TTL, de-myelin routes with >30% escalation, promote frequent patterns to FAQ, write VpT daily.

| Phase | Result | Why |
|---|---|---|
| Scheduler registered | `[PARTIAL]` | In-process APScheduler. Missing dependency in requirements. Multi-worker duplication. |
| Prune cache | `[FAIL]` | Deletes from `semantic_cache` (unused). **Does not talk to Redis.** Exact cache is untouched. |
| Strengthen TTL | `[FAIL]` | Updates `semantic_cache.ttl_seconds`. Redis TTLs unchanged. |
| De-myelin high escalation | `[PARTIAL]` | Query is plausible **if** `route_class` and `model_used` were logged correctly. `LIKE '%sonnet%'` includes **forced** Sonnet (stakes/cortical), not only quality escalations — will false-reset high-stakes routes. |
| Promote to FAQ | `[FAIL]` | Groups `request_log.query_hash`, which is **never inserted**. Inner fetch ignores the group key and takes the global hottest `semantic_cache` row (also empty). If this ever worked, it would auto-publish answers into a pre-LLM FAQ **with no review**. |
| VpT daily | `[PARTIAL]` | SQL is fine. Depends on `vpt` being written (often NULL). `ON CONFLICT` for “today” vs `DATE(ts) = CURRENT_DATE - 1` is internally consistent if run after midnight. |
| Manual `/v1/admin/sleep` | `[FAIL]` as ops | Unauthenticated, returns before work finishes, no lock, no audit user. |

Biological mapping: synaptic homeostasis / systems consolidation is a metaphor. The job does not inspect the live cache, does not replay traces, and does not validate answers. It is a broken cron.

### 4.11 Provider / “5-line Bedrock swap”

Current `invoke()`: ignore the prompt except for substring keys `triage|email_draft|inbox_check`, return canned text, set `tokens_in = context_tokens` (the compressor’s estimate), `tokens_out = random`.

Handoff swap: create a **synchronous** `boto3.client` inside an async function (blocks the event loop under load), `invoke_model` once, no timeout, no retry, no circuit breaker, no guardrails, no usage from a real tokenizer on the compressed prompt, no AWS profile wiring, no Bedrock inference-profile IDs that many Claude 3.5 accounts now require, `max_tokens=1024` hardcoded. That is not a 5-line production cutover.

Titan embeddings: never referenced in runtime code. Semantic cache cannot be wired without them **and** a write path.

### 4.12 Telemetry logger

Logged `intent` = `req.intent_hint or "unknown"`.

If a judge types a query in Swagger without `intent_hint` (the normal path), `/v1/stats` buckets those rows as `unknown`. Classifier work is visible only inside JSON `decision_trace`.

`quality_score` column exists in schema and is never written.

`query_hash` exists and is never written — which also kills sleep FAQ promotion.

### 4.13 Dashboard

Does poll every 5s. Does show KPIs that reflect `request_log` (i.e. the invented accounting).

Defects:

- `innerHTML` interpolation of `feature_class`, `intent`, `reason` — stored XSS if an attacker can `POST /v1/route` (they can; no auth).
- `window.GleanBridge.postMessage` throws in ordinary Chrome (`GleanBridge` undefined). Polling still starts before that script.
- Feature-class names from the client rendered as HTML.
- Stakes panel uses `gate_fired IS NOT NULL`, so `ras.faq` appears as a “Stakes Gate Trip”.
- CDN script `echarts` from jsDelivr — supply-chain + CSP none.
- File opened from disk, CORS `allow_origins=["*"]`.

### 4.14 Demo de-myelination script

Hardcoded DSN `postgresql://clever:clever@localhost:5432/clever`. Sets n=55, lies about phase and LCB, then waits for Enter and zeros the row. Useful as a theatrical reset. Invalid as evidence that L8 “reacts to a bad response”.

---

## 5. Independent math (recomputed)

Environment: Python 3.13.2, `math.sqrt` of the same Beta variance formula as the code.

| Case | α | β | p̂ | σ | LCB | Code decision at τ=0.90 |
|---|---|---|---|---|---|---|
| Prior | 1 | 1 | 0.5000 | 0.2887 | −0.0658 | cold start if n<30 |
| Demo script | 50 | 5 | 0.9091 | 0.0384 | **0.8338** | `cheap_ineligible` (and Myelinating, not Cerebellar) |
| Handoff “unlock” | 95 | 5 | 0.9500 | 0.0217 | **0.9075** | `cheap_ok` if n_obs≥100 |
| First success insert | 2 | 1 | 0.6667 | 0.2357 | 0.2047 | ineligible |

Compressor identity: `8200 → 1220 = 85.1%` exactly as advertised, from constants.

Accounting identity (Haiku 1220/180 vs Sonnet 8200/180 at code prices): **~93.8%**. The “up to 93.9%” is this identity with a slightly different random `tokens_out`.

These numbers will print in Swagger and on the dashboard. They will not survive a tokenizer or a Bedrock bill.

---

## 6. Security (enterprise / Cvent)

Assume Cvent collections: invoice balances, account IDs, contacts, dispute text. That is confidential financial customer data. Treat this as an **externalizable service** that would sit in front of Bedrock.

### 6.1 Control checklist

| Control | Result | Detail |
|---|---|---|
| Authentication on `/v1/route` | `[FAIL]` | None |
| Authorization / tenant isolation | `[FAIL]` | No tenant_id in cache key, DB, or logs |
| Authentication on `/v1/stats` | `[FAIL]` | Cost + traces + gate reasons world-readable on the port |
| Authentication on `/v1/admin/sleep` | `[FAIL]` | Anyone can trigger maintenance |
| mTLS / service identity | `[FAIL]` | |
| Rate limiting | `[FAIL]` | |
| Request size limit | `[FAIL]` | Unbounded `query` / `context` |
| Input schema (allowlisted feature_class, intent) | `[FAIL]` | Free strings |
| CORS | `[FAIL]` | `allow_origins=["*"]`, all methods, all headers |
| TLS | `[FAIL]` | HTTP localhost demo |
| Security headers | `[FAIL]` | |
| Secrets management | `[FAIL]` | Compose password `clever`; DSN default in `config.py`; demo script embeds DSN; `.env.example` has the same password. `.gitignore` does ignore `.env` (`[PASS]` for git hygiene). |
| Redis AUTH / bind | `[FAIL]` | No requirepass, `6379:6379` |
| Postgres network | `[FAIL]` | `5432:5432`, trivial password, no SSL in DSN |
| Dependency pin completeness | `[FAIL]` | `requirements.txt` does not list `asyncpg`, `redis`, `apscheduler`, `openpyxl`. File starts with a UTF-8 BOM. Local import test: `redis` and `apscheduler` missing. |
| SQL injection | `[PASS]` | Parameterized `$1` / `$2` in app SQL. Tail-cost f-string only inlines a hardcoded fragment `AND intent = $2`. |
| Prompt injection | `[FAIL]` | User query concatenated into the prompt. No boundary, no untrusted-content wrapping. |
| Indirect injection via FAQ | `[FAIL]` | Sleep is designed to promote traces into FAQ auto-answers (broken today; dangerous if fixed naively). |
| Insecure output handling | `[FAIL]` | Dashboard XSS; RAS returns DB fields raw |
| Human-in-the-loop for mutate | `[FAIL]` | String prefix only |
| PII minimization | `[FAIL]` | Full `decision_trace` JSONB; Redis stores full response; `aging_data.contact` |
| Encryption at rest | `[FAIL]` | Default Docker volumes, no disk encryption specified, Redis unencrypted |
| Encryption in transit (app↔DB/Redis/Bedrock) | `[FAIL]` | `postgresql://` not `postgresql://...?sslmode=require`; Redis `redis://` not `rediss://` |
| Audit trail of who called | `[FAIL]` | No actor, no request id, wrong intent column |
| Log injection / secret leakage | `[PARTIAL]` | Health returns exception strings to the client |
| OpenAPI exposure | `[FAIL]` | `/docs` on the same port |
| Admin surface | `[FAIL]` | Unauthenticated sleep |
| Multi-instance safety | `[FAIL]` | In-memory scheduler, no leader election |
| Supply chain (dashboard CDN) | `[FAIL]` | |
| SBOM / pinned hashes | `[FAIL]` | Floating lower-bounds on pydantic/yaml/asyncpg (asyncpg not even listed) |
| Code generators in repo | `[PARTIAL]` | `step3_files.py` … `step8_novel.py` rewrite source if executed. Footgun. |
| Tests / SAST / DAST | `[FAIL]` | No tests at all |
| Bedrock least privilege | `[FAIL]` | No IAM policy in repo; mock anyway |
| Guardrails / content filters | `[FAIL]` | |
| Data residency / model region control | `[PARTIAL]` | `AWS_REGION` setting exists, unused by mock |
| Backup / restore | `[FAIL]` | Volume exists; no backup job, no restore runbook |
| Vulnerability disclosure of mock data | n/a | Mock responses contain fake account numbers that look real — fine for demo, bad if mixed with real aging data later |

### 6.2 OWASP API Top 10 (2023) mapping

| ID | Result | Notes |
|---|---|---|
| API1 Broken object level auth | `[FAIL]` | Any account id in a “what is balance on 4021” query is enough, once `aging_data` is loaded |
| API2 Broken auth | `[FAIL]` | |
| API3 Broken object property level auth | `[FAIL]` | Caller decides `context` contents |
| API4 Unrestricted resource | `[FAIL]` | No limits; cascade can double-call; stats full scans |
| API5 Broken function auth | `[FAIL]` | Admin sleep, stats, route all equivalent |
| API6 Unrestricted business flow | `[FAIL]` | `intent_hint=remit`, `stakes=read` still trips mutate via intent, but `campaign_send` does not; `stakes=read` + keyword remit **does** trip (intent wins). Inconsistent. |
| API7 SSRF | `[PASS]` | No fetch of caller URLs |
| API8 Security misconfig | `[FAIL]` | CORS *, open ports, default passwords, `/docs` |
| API9 Inventory | `[FAIL]` | Mock vs real provider not flagged in `/health` |
| API10 Unsafe consumption of APIs | `[FAIL]` | Future Bedrock response accepted as Sonnet quality=1.0 |

### 6.3 OWASP LLM Top 10 (high level)

| Issue | Result |
|---|---|
| LLM01 Prompt injection | `[FAIL]` |
| LLM02 Insecure output handling | `[FAIL]` (XSS, unsanitized RAS text) |
| LLM03 Training data poisoning | `[PARTIAL]` — FAQ/sleep promotion path is the poisoning route |
| LLM04 Model DoS | `[FAIL]` — no max tokens on input, no timeout |
| LLM05 Supply-chain | `[FAIL]` |
| LLM06 Sensitive info disclosure | `[FAIL]` — structured lookup of AR data without auth |
| LLM07 Insecure plugin/agency | `[FAIL]` — “actions” are not real, but the design pretends they are gated |
| LLM08 Excessive agency | `[PARTIAL]` — not wired to side effects **yet**; stakes text implies they exist |
| LLM09 Overreliance | `[BLOCKER]` — dashboard numbers invite overreliance |
| LLM10 Model theft | n/a |

### 6.4 If aging Excel is loaded tomorrow

This becomes the highest-severity issue in the repo: **unauthenticated financial data lookup** over HTTP, plus Redis copies of model answers, plus a browser dashboard.

Do not load production aging files into this stack.

---

## 7. Operational guidance (as a Cvent service)

The handoff “start-of-day routine” is intern-laptop ops: venv, compose up, `docker cp` schema, paste FAQ SQL, `uvicorn --reload`. That is acceptable for a hackathon. It is not operational guidance for an enterprise service.

| Ops capability | Result | Gap |
|---|---|---|
| Documented local boot | `[PARTIAL]` | Windows-specific, paths `C:\CLEVER`, FAQ seed incomplete vs “5 entries” |
| Reproducible installs | `[FAIL]` | `requirements.txt` cannot boot the app (`redis`, `apscheduler` missing). Handoff lists packages the file does not contain. |
| Schema migrations | `[FAIL]` | `CREATE IF NOT EXISTS` + `ALTER ADD COLUMN IF NOT EXISTS` via docker cp. No versioning, no rollback. |
| Config management | `[PARTIAL]` | pydantic-settings + `.env`. Defaults embed credentials. YAML not the runtime source of truth for stakes. CWD-relative `Path("config/intents.yaml")` breaks if uvicorn is not started from the project root. |
| Secrets | `[FAIL]` | See §6 |
| Health vs readiness | `[PARTIAL]` | Single `/health` that is actually a readiness probe. No separate liveness. Exceptions leaked. Does not report `provider=mock`. |
| Metrics (Prometheus/OTel) | `[FAIL]` | |
| Distributed tracing / request-id | `[FAIL]` | |
| Structured logs to SIEM | `[FAIL]` | stdlib logging, no correlation id |
| Alerting | `[FAIL]` | TCR and VpT alerts log or are dead code |
| SLOs / error budgets | `[FAIL]` | |
| Horizontal scale | `[FAIL]` | In-process scheduler; myelination detached tasks; no queue |
| Backpressure / timeouts to LLM | `[FAIL]` | |
| Idempotency | `[FAIL]` | |
| Runbook (incident, Bedrock outage, poison FAQ) | `[FAIL]` | |
| On-call | `[FAIL]` | |
| Backup / PITR | `[FAIL]` | |
| DR region | `[FAIL]` | |
| Change management | `[FAIL]` | Generator scripts overwrite code |
| Environment split | `[PARTIAL]` | `CLEVER_ENV` exists, unused for behavior (CORS, docs, admin stay on) |
| Load test | `[FAIL]` | |
| Gold set / eval harness | `[FAIL]` | `harness/gold_set.gitkeep` empty |
| Model-quality regression | `[FAIL]` | Quality scorer is lexical |
| Feature flags | `[FAIL]` | |
| Dashboard as Superblocks | `[FAIL]` | Static HTML in `superblocks/` |
| Worker concurrency | `[FAIL]` | `asyncpg` pool 2–10; no global cap vs Bedrock TPM |
| Python version | `[FAIL]` | Handoff 3.14, spec 3.12, this host 3.13.2 |
| Windows proxy notes | `[PASS]` as laptop guidance | `pip.ini` trusted-host is a real Cvent-network gotcha, not a product control |
| `--reload` in start script | `[PARTIAL]` | Correct for demo; dangerous if copied to a server |
| Observability of savings | `[BLOCKER]` | Metrics defined against a fake baseline; cannot be used for FinOps |

**Start-of-day routine defects**

1. No wait-for-healthy Postgres before `psql -f schema`.
2. Schema apply is manual and non-idempotent in practice (operators will skip/double-run).
3. FAQ seed uses `ON CONFLICT (question)` — good — but only two rows.
4. No instruction to **not** publish 5432/6379 on a shared network.
5. Swagger “Edit Value” tip is real (JSON `{{` issue) and is the most honest ops note in the handoff.
6. Flush Redis before myelination tests — implicit admission that cache hides the layer being demoed.

---

## 8. What the handoff gets right

Credit where the code matches:

1. There is a single orchestrator; layer order is mostly as described.
2. Stakes on `remit` / `email_blast` / `stakes=mutate` does skip RAS and cache and force Sonnet (in the mock).
3. Empty `aging_data` does not crash structured lookup.
4. Postgres parameterization is consistently used.
5. Cache and myelination errors are caught and degraded rather than 500’ing (except a hard pool failure at startup).
6. `.gitignore` excludes `.env` and `*.xlsx`.
7. Handoff **admits** Bedrock is mocked, semantic cache is unwired, aging is empty, quality `mock_signal` is an artifact. Those admissions are accurate.
8. The Cerebellar LCB example (α=95, β=5) is arithmetically correct.
9. Runtime Python files parse (syntax OK).

Honesty in the handoff stops at the “verified in testing” list and the 85.1% / 93.9% figures. Those sections read as measured. They are not.

---

## 9. Defect register (severity)

### Blockers (do not demo as fact; do not ship)

| ID | Item |
|---|---|
| B1 | Token and cost savings are functions of hardcoded 8200 / 300 / list prices / mock usage, not Bedrock |
| B2 | No authentication on route, stats, or admin |
| B3 | Human-confirm is a string prefix after the call |
| B4 | Zero automated tests; no gold set |
| B5 | `requirements.txt` does not install the app (`redis`, `apscheduler` absent; `asyncpg` absent from the file) |
| B6 | Structured lookup will leak AR data the moment Excel is loaded |

### High

| ID | Item |
|---|---|
| H1 | Cache key omits context; cross-account answer reuse |
| H2 | Cache HIT not logged; HIT accounting not $0 |
| H3 | Logger stores `intent_hint`, not classified intent |
| H4 | Myelination treats forced Sonnet as success; critical reset dead |
| H5 | `campaign_send` (and other mutate-like intents) not gated |
| H6 | Sleep FAQ promote broken; if fixed without review it is a poisoning vector |
| H7 | Open Redis/Postgres with default passwords, published ports |
| H8 | Dashboard XSS + CORS `*` |
| H9 | Cascade drops Haiku cost on escalate |
| H10 | Default mock path always “quality-fails” because of `[MOCK]` in the string |

### Medium

| ID | Item |
|---|---|
| M1 | FAQ is `ts_rank`, threshold 0.01, labeled BM25 |
| M2 | Invoice resolver missing; INV numbers parsed as accounts |
| M3 | Template `_days_from_now` uses the wrong regex group |
| M4 | YAML intents/features far smaller than claimed |
| M5 | Sleep prunes unused `semantic_cache`, not Redis |
| M6 | Stats “stakes trips” include RAS hits |
| M7 | Demo script mislabels phase and eligibility |
| M8 | VpT dollars are fiction; RAS discards VpT |
| M9 | Generator scripts can overwrite production files |
| M10 | CWD-relative YAML paths |
| M11 | No indexes on `request_log` for the stats queries |
| M12 | In-process weekly cron |

### Low

| ID | Item |
|---|---|
| L1 | `datetime.utcnow()` deprecated in sleep |
| L2 | UTF-8 BOM on `requirements.txt` / `.gitignore` / `.env.example` |
| L3 | Empty `__init__.py` files (harmless) |
| L4 | `httpx` in requirements, unused |
| L5 | GleanBridge throw in stock Chrome |
| L6 | Health leaks exception text |
| L7 | Schema comment mojibake (`�12`) |

---

## 10. What would have to be true before this is “real”

Minimum bar for a **technical** (still not enterprise) proof:

1. Real Bedrock (async client, timeouts, retries, actual `input_tokens`/`output_tokens`).
2. Real tokenizer on the **unprojected** vs **projected** prompt; delete the `8200` constant.
3. Aging loader + tests that structured lookup returns the right row for account **and** invoice, and does not match `INV-2024-*` as account `2024`.
4. AuthN at the gateway (service token) before any RAS DB read.
5. Cache key includes canonical context (or a server-side fetched record id + version).
6. Telemetry logs classified intent, query hash, both legs of a cascade, cache hits, request id.
7. Myelination success = cheap model accepted **by a real quality check**, not `not escalated`.
8. Stakes list driven from YAML; mutate intents cannot cache; human confirm is a second authenticated call.
9. FAQ: real BM25 or a named ranker, threshold tuned on labeled pairs, human approval for promotion.
10. `requirements.txt` complete and hashed; tests covering classifier, stakes, RAS, cache key, myelination LCB, accounting with fixtures.
11. Sleep: operate on Redis, never auto-FAQ without review, single-leader lock.

Minimum bar for **Cvent production**: everything above, plus SSO/service mesh, TLS everywhere, secret store, private DB/Redis, tenant isolation, PII handling, eval harness vs a labeled gold set, FinOps using **AWS Cost Explorer / Bedrock usage**, not this baseline formula, and a threat model signed by security.

---

## 11. Check-mark dump (everything asked)

### Architecture & novelty mechanism (implementation, not literature)

- `[PARTIAL]` Pre-LLM filtering exists (rules + SQL + FAQ + cache)
- `[FAIL]` It is not RAS in any scientific sense
- `[PARTIAL]` Beta-Bernoulli routing exists
- `[FAIL]` Progressive unlock is trained on the wrong success signal
- `[FAIL]` Sleep consolidation does not maintain the live system
- `[FAIL]` Combination is not demonstrated as an empirically validated system (no eval)

### Data

- `[FAIL]` `aging_data` empty, no loader
- `[PARTIAL]` FAQ table exists, seed is manual and incomplete
- `[FAIL]` Semantic cache empty and unwired
- `[PARTIAL]` `request_log` written on some paths, wrong columns
- `[PASS]` pgvector extension declared

### Cost story

- `[BLOCKER]` 85.1% compression
- `[BLOCKER]` 93.9% savings
- `[PARTIAL]` RAS $0 path (true for mock, hardcoded 100%)
- `[FAIL]` Baseline is not “what Cvent would have spent”

### Security

- `[FAIL]` AuthN
- `[FAIL]` AuthZ
- `[FAIL]` Tenant isolation
- `[FAIL]` Secrets
- `[FAIL]` Network exposure
- `[PASS]` Parameterized SQL
- `[FAIL]` Prompt injection
- `[FAIL]` Human confirm control
- `[FAIL]` PII
- `[FAIL]` Admin lock
- `[FAIL]` Rate limit
- `[FAIL]` TLS

### Operations

- `[PARTIAL]` Local compose
- `[FAIL]` Install reproducibility
- `[FAIL]` Migrations
- `[PARTIAL]` Health check
- `[FAIL]` Metrics/tracing
- `[FAIL]` Alerts
- `[FAIL]` Backups
- `[FAIL]` Tests
- `[FAIL]` Runbooks
- `[PARTIAL]` Handoff as intern notes (useful), not as ops manual

### Handoff integrity

- `[PASS]` Mock Bedrock admitted
- `[PASS]` Semantic cache gap admitted
- `[PASS]` Aging empty admitted
- `[FAIL]` “Verified in testing” numbers
- `[FAIL]` 25+ intents / 14 feature classes
- `[FAIL]` campaign_send trips stakes
- `[FAIL]` BM25
- `[FAIL]` Cache HIT ~$0 as accounting
- `[FAIL]` 5-line production Bedrock swap
- `[FAIL]` “all core + novel layers” as production-quality

---

## 12. Bottom line

CLEVER is a **demo of an architecture diagram**. Several ideas in it are standard and worth building: don’t send mutate traffic to a cheap model; don’t send a whole aging workbook when four fields will do; cache exact repeats behind a data version; keep a success rate per route; log cost.

The current repo **does not prove** those ideas. It **prints** them, using constants and a mock.

Treat v0.2.0 as intern milestone code. Do not load real Cvent data. Do not quote 85.1% or 93.9% outside the room where everyone has seen `compressor.py` line `_FULL_CONTEXT_TOKENS = 8_200`. Do not describe Stakes Gate as a financial control. Do not describe Sleep as self-maintenance until it mutates Redis/FAQ with tests and a review queue.

If the next phase is a hard proof rather than a better pitch: instrument real Bedrock tokens, add an eval harness, add auth, and replace every hardcoded baseline with a measured one. Until then the honest status line is:

**Mock gateway, synthetic savings, no tests, no security boundary.**

---

*End of analysis. Code reviewed in `CLEVER-main/`. Handoff: `CLEVER_Project_Handoff_for_LLMs.md`.*
