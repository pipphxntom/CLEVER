# CLEVER v0.5.0 — Routing & Sleep evaluation (honest)

**Date:** 2026-08-23  
**Gateway:** `0.5.0`, `openai_compat` (the live API `cheap-model` / `strong-model`)  
**This file is the evaluation of the Thompson routing + sleep work.** It is not a savings press release.

**Raw artifacts:**

| Artifact | What it is |
|---|---|
| `harness/last_routing_sleep_api.json` | Live HTTP probe, **18/18 second pass** |
| `tests/test_myelination.py`, `tests/test_sleep.py`, `tests/test_thompson_sim.py` | Unit / simulation |
| `CLEVER_Routing_Sleep_Research_Handoff.md` | Design doc. **Not code. Several claims were wrong.** |
| `CLEVER_Final_API_Savings.md` | A–H live savings under **v0.4.0** and **`N_MIN=6`**. Not re-run for v0.5. |
| `version_control_v0.5.0.md` | File-level change list |

**Process knobs on the live gateway (from `.env`, not `config.py` defaults):** `N_MIN=6`, `N_EXPLORE=3`. Production defaults remain `N_MIN=30`, `N_EXPLORE=10`. Sleep interval default `604800` s (7 days).

---

## 0. Verdict in one paragraph

Thompson routing and testable sleep **work as mechanisms on a live HTTP API gateway**, when the request actually reaches myelination and when sleep is triggered by hand. They did **not** fail as a rewrite of RAS / stakes / exact cache. They also did **not** prove the research handoff’s 23–38% production savings, did **not** learn from a cold registry to lock-in without seeding, and did **not** run a week of unattended sleep.

The first live pass looked like 14/18 failed. **Three of those were a harness bug** (`0.0 or 1` in Python). **One was real:** semantic cache HIT `sim=0.930` skipped myelination, so “first cheap explore” never ran. After flushing Postgres `semantic_cache` and isolating context, explore/lock-in/lock-out and sleep decay all passed.

**Do not tell a judge “we invented brain-inspired routing and it saved 38%.”** Tell them: we replaced an over-conservative Wilson LCB gate with Thompson Sampling plus a credible lock, kept the same Beta update, forced the first cheap trial after cold so the posterior can move, and we can fire sleep on demand. Simulation says that beats LCB at production `N_MIN=30`. Live, we showed the **gates fire**. We did not show organic savings.

---

## 1. What we set out to do

Stuck problem from v0.4.0 / novels status:

- **Routing:** Wilson LCB + fixed `N_EXPLORE` almost never unlocked cheap at production `N_MIN=30`. A–H only saw flash because `.env` had `N_MIN=6`. Test-2: one quality fail could burn the explore budget. Cheap routing was “a mechanism,” not a result.
- **Sleep:** weekly cron, never proven live. Pruned Postgres `semantic_cache`. FAQ promotion grouped on `query_hash`. No consolidation log. Could not be tested without waiting a week or hitting `/v1/admin/sleep` with no decay/log story.

Research handoff (2026-08-23) proposed: replace LCB with Thompson + Bayesian credible lock-in/out; make sleep interval-configurable; decay α/β; quality-gated FAQ **candidates**; Redis cache maintenance.

Constraint we kept: **do not regress RAS, stakes, compression, exact cache, or the Beta update rule.** Do not lower production `N_MIN` or τ to print a slide.

---

## 2. What we actually built (v0.5.0)

### 2.1 Routing — decision only

| Piece | Done? | Notes |
|---|---|---|
| `beta_credible()` + Thompson sample vs τ | **Yes** | Stdlib only (`math.lgamma`, `random.betavariate`) |
| Lock-in when `P(p>τ) ≥ 0.90` | **Yes** | Deterministic cheap |
| Lock-out when `P(p>τ) ≤ 0.01` | **Yes, with a guard** | Requires `LOCK_OUT_MIN_CHEAP=10` |
| First cheap trial after cold | **Yes — extra vs handoff** | Without this, Beta(1,1) vs τ=0.92 samples above τ ~8% of the time |
| Beta update (α+=1 / β+=1 / strong n_obs+=1) | **Unchanged** | Critical reset now also zeros `cheap_n` |
| `N_MIN` production default 30 | **Kept** | `COLD_MIN` aliases it. Live process still loaded **6** from `.env` |
| Remove `N_EXPLORE` | **No** | Still in config so old `.env` is not a surprise. It is **not** an explore budget |
| Wilson LCB | **Diagnostic only** | Still on the trace as `lcb`. Routing uses `eligible` / `credible` |
| Trace fields `credible`, `thompson_sample`, `tau` | **Yes** | Pipeline JSONB |

### 2.2 Sleep

| Piece | Done? | Notes |
|---|---|---|
| `SLEEP_INTERVAL_S` scheduler | **Yes** | Default 7 days, not Sunday 03:00 cron |
| `POST /v1/admin/sleep` + `/v1/admin/consolidate` | **Yes** | Admin key required |
| Redis lock acquired **and released** | **Yes** | Old job held the lock 3600s; that blocked re-test |
| Decay α/β, keep n_obs | **Yes** | Evidence decay `(α-1, β-1)×0.80`, not `α×0.80` |
| FAQ candidates, not live FAQ | **Yes** | Quality floor 0.95, min 0.85, threshold 5 |
| `consolidation_log` | **Yes** | `schema_v05.sql` |
| VpT daily aggregation | **Kept** | Handoff rewrite would have dropped it |
| Prune Postgres `semantic_cache` zero-hit | **Kept** | That table **is** the semantic cache |
| Extend Redis exact keys via `query_hash` | **Refused** | Exact key is `exact:{version}:{payload_hash}`. Not `query_hash`. Implementing it would have been fake |

### 2.3 Files not modified (on purpose)

`gateway/layers/cache.py`, `ras_gate.py`, `stakes_gate.py`, `compressor.py`, `cascade.py`, `quality.py`, `telemetry/accounting.py`.

---

## 3. Research handoff vs the running system

The handoff was a design document. Several statements were **false or stale** against v0.4.0 code. We did not implement those blindly.

| Handoff claim | Check against code | Action |
|---|---|---|
| `query_hash` is never written | **False.** `telemetry/logger.py` already writes it | Hash function **not** replaced |
| `faq_candidates` missing from schema | **False.** Created in `schema_v03.sql` | v0.5 **ALTERs** extra columns |
| Sleep prunes the “wrong” cache | **Half.** Postgres `semantic_cache` is the semantic cache (`hit_count` is real). Redis is exact cache with a different key | Prune Postgres; skip fake Redis EXPIRE |
| Naive Thompson after cold | **Broken.** After strong-only cold, α=1, β=1. One cheap fail → Beta(1,2) → `P(p>0.92)≈0.006` → lock-out forever | Forced first explore; lock-out min 10 cheap trials |
| `α,β × 0.80` reduces confidence | **False as written.** `Beta(51,3)→(41,2)` **raises** `P(p>0.92)` (0.807 → 0.860) because rounding deletes a failure | Decay evidence `(α-1, β-1)` → `(41,3)`, which **does** drop confidence |
| COLD_MIN=10 | Conflicts with prior handoff: “do not lower N_MIN to print a slide” | Default stays **30** |
| 23–38% live savings | Simulation, not an API result | Kept as simulation; see §5 |

---

## 4. Unit / simulation observations

`python -m pytest -q` → **73 passed** (after two tests were rewritten to match real math, not the handoff’s hoped-for numbers).

| Observation | Evidence |
|---|---|
| Cold start still blocks cheap | `n_obs=0` → `cold_start`, `eligible=False` |
| First explore is forced | `n_obs=N_MIN`, `cheap_n=0` → `explore` |
| Lock-in is deterministic | α=99, β=2 → `locked_cheap`, no `thompson_sample` |
| Lock-out needs enough cheap trials | α=1, β=2, `cheap_n=1` stays Thompson; α=2, β=20, `cheap_n=21` → `locked_strong` |
| `beta_credible(9,1,0.92)` ≈ 0.50 | Matches `1−0.92^9` (handoff unlock table, 8 successes) |
| LCB at production settings barely saves | 500-req sim, cheap 96% good, `N_MIN=30`: LCB **~1%** vs all-strong |
| Thompson on the same mix | **23–41%** depending on seed (handoff 32–38% is in-band, seed-sensitive) |
| Cheap actually bad (p=0.50) | Thompson **~0%**, self-corrects; no fake win |
| Degradation 96%→75% at t=300 | Mean Thompson save **~18%** over 5 seeds. Seed 3 was **4.9%**. We did not cherry-pick |

Simulation is **not** live HTTP API. Cheap=0.5 / strong=1.0 / escalate=1.5 is a toy cost model.

---

## 5. Live API observations (the live API)

Harness: `python -m harness.run_routing_sleep_api`  
Spend this session: **~$0.002** (first pass ~$0.000975 + second ~$0.001375).

### 5.1 Pass 1 — 14/18 (do not bury this)

| Case | Printed actual | Real status |
|---|---|---|
| `pipeline.ras_date` | `hit=ras.template cost=0.0 tokens=0` | **Worked.** Harness treated `0.0` as missing |
| `pipeline.stakes_remit` | `pending_confirmation tokens=0 cost=0.0` | **Worked.** Same harness bug |
| `pipeline.cache_after_sleep` | `first_passed=True second_hit=True second_cost=0.0 tier1=cheap` | **Worked.** Same harness bug |
| `routing.first_explore_after_cold` | `decision=None … score=0.930…` | **Real fail.** Gateway log: `cache.semantic HIT sim=0.930 id=26` |

Gateway log on the explore miss (abridged):

```
cache.exact MISS
cache.semantic HIT sim=0.930 id=26
```

Myelination never ran. Score `0.930` was **cosine similarity**, not a quality score. This is the same class of bug that hid cheap routing in Test-2 / A–H: **cache sits in front of the thing you think you are measuring.** Flushing Redis is not enough; semantic cache is Postgres.

Other pass-1 facts that *did* work before the re-run:

- Cold start → strong (`cost=0.000219`)
- n_obs=5 stays cold under process `N_MIN=6`
- Lock-in α=99,β=2 → `locked_cheap`, **flash final, no escalate**, `credible=1.0`, diagnostic `lcb=0.956`
- Lock-out → `locked_strong`, cheap not tried
- Sleep: decay 51,3 → 41,3; candidate on 0.97; no candidate on 0.70; FAQ not published; log written; lock released
- Cold **dispute** quality **0.75** (`required_fields` fail vs floor 0.92). Routing was correct (strong). The answer was still a weak strong-tier draft. That is quality/context, not Thompson.

### 5.2 Pass 2 — 18/18 after isolation

Fixes: compare zeros without `or 1`; `DELETE FROM semantic_cache` before routing probes; unique `invoice_ids` on the explore query.

| Check | Intended | Actual | Worked? |
|---|---|---|---|
| Health | db/redis ok, v0.5.0 | `openai_compat` | Yes |
| Auth | 401 without keys | 401 on route and consolidate | Yes |
| RAS date | $0, no tokens | template HIT, 0/0 | Yes — **not broken by v0.5** |
| Remit | pending, no LLM | pending, tokens=0 | Yes |
| Cold start | strong, no cheap | `cold_start`, strong, $0.000523 | Yes |
| Below N_MIN | n_obs=5 still cold | `cold_start` | Yes **for N_MIN=6** |
| First explore | `explore`, cheap_tried | `explore`, **tier=cheap, score=1.0, no escalate** | Yes |
| Lock-in | `locked_cheap` | `locked_cheap`, cheap final, `lcb=0.956` still logged | Yes |
| Lock-out | `locked_strong` | strong, cheap_tried=false | Yes |
| Consolidate | 200, status=ok | 77 ms, decayed=3, candidates=2 | Yes |
| Decay | 51,3 → 41,3, n_obs=55 | exact | Yes |
| Pattern gate | good hash pending; bad hash absent | exact | Yes |
| No auto-FAQ | faq_entries unchanged | 2→2, source=sleep is 0 | Yes |
| Log + lock | grow log; second POST not skipped | `/v1/admin/sleep` status=ok | Yes |
| Second decay | 41,3 → 33,3 | exact | Yes |
| Exact cache after sleep | HIT if quality passed | HIT, $0, first was cheap | Yes |

`candidates=2` / `patterns_found=2` on pass 2 is leftover **plus** the new hash: pass 1 already inserted a 0.97 pattern still inside the 7-day window. Not a double-publish into live FAQ.

---

## 6. Evaluation: routing

### Worked as intended

1. **Decision function replacement.** Live traces show `cold_start`, `explore`, `locked_cheap`, `locked_strong`. Pipeline still keys off `eligible`. Cheap was actually called on explore and lock-in, and **produced the final answer** (quality 1.0, no escalate) on those seeded dunning drafts.
2. **Cold start not loosened.** n_obs=0 and n_obs=5 (with this process N_MIN=6) stayed on strong.
3. **Lock-in is earlier than Wilson LCB.** Seed α=96,β=5 used to be `cheap_ineligible` (LCB~0.901 < 0.92). Thompson lock-in on α=99,β=2 fired live. Diagnostic LCB on that seed was 0.956 — coincidentally also above τ — but the **gate** was `credible=1.0`, not LCB.
4. **Lock-out stops a bad posterior** from taking more cheap shots once `cheap_n` is large.
5. **Existing short-circuits still work.** Date RAS and remit hold were $0 on the same live process.

### Failed, or only worked under caveats

| Claim | Status |
|---|---|
| “Thompson explores naturally from Beta(1,1) after cold” | **Failed as specified.** We had to **force** the first cheap trial. That deviation is load-bearing. Without it the design reintroduces the v0.3 cold-start deadlock. |
| “No N_EXPLORE needed” | **Partly failed.** The budget is gone, but a **first-trial** exception exists, and lock-out still needs a minimum cheap count. |
| Organic cheap unlock on live traffic | **Not demonstrated.** Registry rows were **seeded**. Nobody walked a cold route to 27 cheap successes on the live API. |
| Production N_MIN=30 on the live gateway | **Not this run.** `.env` is still `N_MIN=6`. The below-N_MIN test proves 6, not 30. |
| Routing save % on mixed traffic | **Not measured for v0.5.** A–H 43.7% is v0.4.0 + eval knob. Do not reuse it as a Thompson result. |
| Semantic cache vs routing | **Interference, by design.** Pass 1 explore was a **false miss** of the routing layer. Any demo that paraphrases “draft email to Ada…” without flushing **Postgres** semantic cache is not a routing demo. |
| Dispute quality on cold strong | **Pre-existing fail.** score 0.75, missing required fields. Thompson did not cause it and did not fix it. |

**Honest routing grade:** **mechanism pass, result not yet a savings result.** Better than v0.4.0’s “cheap never a live final” *on this seeded probe*. Not a production myelination paper.

---

## 7. Evaluation: sleep consolidation

### Worked as intended

1. **Testable.** Manual trigger, 77 ms, no 7-day wait.
2. **Decay is real and repeatable.** 51,3 → 41,3 → 33,3. `n_obs` stayed 55 (does not dump the route back into cold).
3. **Quality gate is real.** 5× quality 0.97 created a `pending` candidate. 5× 0.70 created none.
4. **Does not auto-publish FAQ.** `faq_entries` count unchanged. That was the RAS-steal footgun. We kept the safer behavior.
5. **Audit row exists.** `consolidation_log.trigger=manual`.
6. **Lock is not stuck.** Second job ran. Old 1-hour NX lock would have said `skipped_lock`.
7. **VpT daily still runs** (`vpt_days=3` in the job payload).

### Failed, or only worked under caveats

| Claim | Status |
|---|---|
| Redis exact-cache “hot key extend” via `query_hash` | **Not built. Would have failed if built.** Job correctly reports `cache_extend_skipped`. `pruned_meta=0` this run (rows were fresh, not 7 days old). |
| Weekly unattended consolidation | **Not proven.** Scheduler is registered at `SLEEP_INTERVAL_S=604800`. We never waited a week. |
| Pattern detection on **organic** `request_log` | **Seeded hashes.** Logger does write `query_hash` (v0.4.0 already did). We did not wait for 5 natural repeats of a live query. |
| Decay always reduces `P(p>τ)` if you multiply α,β | **Handoff math failed.** Shipped evidence-decay instead. That **did** reduce confidence. |
| Sleep as a “novel consolidation engine” | **Overclaim.** It is maintenance: decay, candidate queue, prune, log. Prior art: cache TTL, log mining, posterior tempering. |

**Honest sleep grade:** **maintenance job pass, novelty fail, production-week unproven.** It does what the rewritten spec (after we corrected the handoff) said, when you POST the admin endpoint.

---

## 8. Did they work or fail? Scoreboard

| Intended outcome | Worked? | Evidence |
|---|---|---|
| Replace LCB as the **gate** | **Worked** | Live `locked_cheap` / `locked_strong` / `explore` |
| Cheap can be the **final** answer | **Worked on seeded live drafts** | explore + lock-in, quality 1.0, no escalate |
| Do not regress RAS / stakes / exact cache | **Worked** | $0 date, pending remit, cache HIT after sleep |
| Sleep can be tested in minutes | **Worked** | Manual consolidate 77 ms |
| Sleep decays routing confidence | **Worked** | 51,3 → 41,3 → 33,3 |
| Sleep does not auto-FAQ | **Worked** | 0 sleep-sourced `faq_entries` |
| Handoff Thompson-from-uniform after cold | **Failed — we patched it** | Forced first trial |
| Handoff `α×0.80` decay | **Failed — we patched it** | Evidence decay |
| Handoff Redis key = query_hash | **Failed as a design — we refused it** | Skip logged |
| 23–38% live production save | **Not shown** | Simulation only |
| Organic lock-in without seeding | **Not shown** | Seeds in the harness |
| Semantic cache will not hide routing | **Failed in pass 1** | HIT 0.930; pass 2 required a flush |
| Production N_MIN=30 live | **Not this gateway process** | `.env N_MIN=6` |

---

## 9. What a judge / next owner should quote

**Quote:**

- v0.5.0 replaced Wilson LCB **gating** with Thompson + Bayesian credible lock. Update rule unchanged.
- Live HTTP API probe: seeded lock-in and first-explore both called flash and **kept** the cheap answer (quality 1.0). Lock-out stayed on pro. RAS/stakes/exact cache still $0 where they should be.
- Sleep is a manual, logged maintenance job that decays posteriors and queues FAQ **candidates**. It does not publish.
- At production `N_MIN=30`, a 500-request **simulation** still shows LCB ~1% vs Thompson ~23–41% when cheap is 96% good.

**Do not quote:**

- 23–38% as a measured API savings number
- A–H 43.7% as a v0.5 Thompson result (wrong version, eval `N_MIN=6`)
- Dashboard `avg_saved_pct`
- “Novel neuroscience / myelination / sleep consolidation science”
- Pass 2 18/18 as “the first run was clean”
- Redis cache maintenance as implemented

---

## 10. Remaining work (if anyone continues)

1. Re-run Groups A–H on v0.5 **twice**: once with `.env N_MIN=6` (comparable to 43.7%), once with `N_MIN` **unset** (production 30). Until then, savings claims stay at v0.4.0.
2. Organic run: empty `myelination_registry`, unique queries, **no** semantic cache, count how many paid calls until `locked_cheap`.
3. Decide whether semantic cache should record `skipped_myelination` in the trace (it currently omits the layer entirely — that is why pass 1 looked like a routing bug).
4. Production sleep: leave the process up 7 days or set `SLEEP_INTERVAL_S=120` in a soak, then read `consolidation_log`. Manual POST is not that.
5. Dispute / required_fields quality fail is still open. Unrelated to Thompson, still a bad strong-tier answer.

---

*End. Prefer this file over the research handoff for what shipped. Prefer `CLEVER_Final_API_Savings.md` for the only live dollar-weighted % we have, and keep its caveats.*
