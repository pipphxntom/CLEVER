# Version control — v0.5.0

| ID | Change |
|---|---|
| R1 | Myelination **decision** is Thompson Sampling + Bayesian credible lock-in/out. Wilson LCB remains a diagnostic `lcb` field only. |
| R2 | Beta **update rule unchanged** (cheap success α+=1, fail β+=1, strong-only n_obs+=1). |
| R3 | `N_MIN` kept (prod 30). `COLD_MIN` aliases it. **Not lowered.** First cheap trial after cold is forced — Beta(1,1) vs τ=0.92 would otherwise almost never explore. |
| R4 | No explore budget. `N_EXPLORE` still accepted from `.env` so existing eval knobs don't surprise. Lock-out requires `LOCK_OUT_MIN_CHEAP` (default 10) so one fail cannot freeze a route. |
| S1 | Sleep interval is `SLEEP_INTERVAL_S` (default 7d). Manual `POST /v1/admin/sleep` and `/v1/admin/consolidate`. Lock released after the job so tests can re-trigger. |
| S2 | Sleep decays α/β, keeps n_obs, quality-gates FAQ **candidates**, prunes Postgres `semantic_cache` (the table it actually owns). Does **not** invent Redis exact-cache keys from `query_hash` — those hashes are different. |
| S3 | `db/schema_v05.sql`: `consolidation_log`, extra `faq_candidates` columns, `query_hash` index. |
| S4 | `query_hash` was already written in v0.4.0. Hash function **not** changed. Logger now also writes truncated `query_text_redacted` for pattern representatives. |
| T1 | Unit tests: Thompson lock-in/out, `beta_credible` vs Monte Carlo, sleep decay math, 500-request sim vs LCB. |

**Not claimed:** live HTTP API savings from Thompson. The 23–38% figures in the research handoff are **simulations**. A–H 43.7% was an eval `N_MIN=6` result and is not reproduced here.
