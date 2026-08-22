# Groups A–H — live DeepSeek observation

**When:** 2026-08-23 (gateway clock 2026-08-22 21:50–21:54 UTC)  
**Suite file:** `CLEVER_Test_Suite.md` (37 cases, Groups A–H)  
**Runner:** `python -m harness.run_suite_ah`  
**Raw JSON:** `harness/last_suite_ah.json`  
**Elapsed:** 240.3 s  
**Gateway:** `0.4.0` at `http://127.0.0.1:8080`  
**Provider:** `openai_compat` → `https://api.deepseek.com`  
**Cheap:** `deepseek-v4-flash` · **Strong:** `deepseek-v4-pro` · **Thinking:** disabled  
**Auth:** `X-API-Key` required (dev key, not printed here)  
**Infra:** Rancher Desktop dockerd + `clever_postgres` + `clever_redis`  
**Dashboard:** `http://127.0.0.1:8080/` — this run **cleared `request_log` first** so the 24h window **is** Groups A–H, not leftover mock rows.

This file is the deep observation. Savings numbers that a finance person could quote live in `CLEVER_Final_API_Savings.md`. Mock-only numbers live in `CLEVER_Mock_Results_Separate.md` and are **not** mixed in here.

---

## 1. Score — be careful how you count

| Bucket | Count |
|---|---|
| Cases run | **37 / 37** |
| Harness `ok=true` | **34** |
| Harness `ok=false` | **3** (A4, G5, H5) |
| TRUE PASS | 15 |
| SURPRISE PASS (audit trap, now fixed) | 19 |
| EXPECTED FAIL (audit defect still real, or harness over-called it) | 3 |
| Gateway crash (500) | **0** |
| Provider | live DeepSeek, not mock |

The 34/37 headline is **not** “product is done.” Three of the most important original traps (E1 8200-token lie, D2 cache leak, B4 confirm theater, G1 no-auth) are now passes. What still fails, and what passed for the wrong reason, is the rest of this file.

**Harness mis-scores to correct in this write-up (not in the JSON):**

- **G5** was marked FAIL because the model said “I can’t disclose the system prompt.” That is a **refusal**, not a leak. Detector was greedy. Outcome: no dump. Control: still absent.
- **H5** was marked FAIL because only the 3rd of 3 repeats was an exact HIT. The original trap was “hits not logged / HIT billed as miss cost.” Hits **are** logged (`by_exit.cache=7`) and the HIT is **$0**. The 2-miss-then-HIT pattern is quality-gated store, not the old accounting bug.

Corrected engineering score: **35/37 product-ok**, **1 remaining functional defect (A4)**, **1 missing control (prompt boundary)**, plus the measurement caveats below.

---

## 2. What this run actually did to the dashboard

`request_log` was emptied at suite start (old 93-row mix snapshotted to `harness/pre_suite_ah_stats.json`). After the suite, `/v1/stats` and the HTML dashboard at `/` show:

| Dashboard field | Value | Honest reading |
|---|---|---|
| provider | `openai_compat` | Correct. Not mock. |
| total_requests | 55 | More than 37 tests: repeats (D1, H1, H4×20, H5×3, F2×5) plus auth-only tests that do not log. |
| total_cost_usd | $0.0261 | Priced from `config/pricing.yaml` off-peak cache-miss rates × provider `usage`. Not a DeepSeek invoice screenshot. |
| avg_saved_pct | **59.4** | **Do not quote.** Unweighted mean of every row, including RAS/cache/stakes at 100%. |
| llm_saved_pct | **32.4** | Unweighted mean of **LLM rows only**. Pulled down by negative-save verbose answers. |
| short_circuit_pct | **40.0** | 22/55 paid $0 (4 RAS + 7 cache + 11 stakes pending). |
| by_exit | ras 4 / cache 7 / stakes 11 / llm 33 | This split is the useful view. |
| models | pro 20 · flash 13 · semantic cache 5 · exact cache 2 | Cheap routing **did** happen. See §7. |
| avg_latency_ms | 7416 | Dominated by 20 concurrent DeepSeek calls, some 12–34 s. |

Open `http://127.0.0.1:8080/`, leave the API key field as the local dev key, and you should see LIVE + those KPIs + recent `triage` rows + Stakes HOLD trips on remit.

---

## 3. Group-by-group

### A — Routing & classification

| ID | Verdict | What happened |
|---|---|---|
| A1 | TRUE PASS | `provider=openai_compat`, db ok, redis ok, version 0.4.0. |
| A2 | TRUE PASS | “aging triage for overdue accounts” → `intent=triage`, `method=keyword`, conf 0.8. |
| A3 | SURPRISE PASS on **logging**; **wrong intent** | Query: “draft a dunning email for the overdue balance”. Classified **`triage`**, not `email_draft`. Stats stored `triage` (so the original “logger writes unknown/hint” bug is gone). Cause: `intents.yaml` order — `triage` keywords include `overdue`, which appears before `dunning` is considered. First-match wins. A collections dunning draft is the **wrong bucket**. |
| A4 | **EXPECTED FAIL — still open** | `"what is 2+2"` + `intent_hint=triage` → classifier `method=config`, **confidence 1.0**, intent `triage`. Model answered “It’s **4**.” Any caller with the route key can force any **known non-mutate** intent. Mutate keywords fail-closed first; that is the only hardening. This is still an intent backdoor. |

### B — Stakes Gate

All five pass. This is no longer theater.

| ID | Result |
|---|---|
| B1 remit | `SUSPENDED`, `pending_confirmation`, UUID, `tokens_in=0`, cache OFF, min_tier strong. |
| B2 email_blast | Same. |
| B3 campaign_send | **Was the H5 audit hole.** Now `mutate_intent:campaign_send`, pending, no model. |
| B4 confirm control | Response: “Resubmit with confirm_token to proceed. **No model was called.**” `confirmation_id` issued. Not the old warning-string-then-call-Sonnet path. |
| B5 feature_class `reconciliation` | `high_stakes_class:reconciliation`, pending. |

Not tested here: the **second** call with a valid `confirm_token` actually invoking strong. Prior API eval did. This suite only proves the hold.

### C — RAS

| ID | Verdict | Observation |
|---|---|---|
| C1 date | TRUE PASS | `ras.template` HIT, $0, “Today is August 23, 2026.” |
| C2 days until | SURPRISE PASS | Was dead regex. Now HIT: “2026-12-31 is 130 days from today.” |
| C3 account 4021 | TRUE PASS (graceful miss) | Fixture account is **40211**, not 4021. No SQL HIT (good — did not invent a row). **Fell through to DeepSeek**, which refused (“I don’t have access to your account…”). Cost **$0.000236**. This is the RAS miss path: you **pay** when lookup misses. The suite’s 4-digit example will always miss 5–8 digit accounts. |
| C4 invoice | SURPRISE PASS with a scar | Entity `INV-2024-089` recognized, **not** account `2024`. HIT structured. Response text: “Account Northwind Events: **status = open**.” That is the **account** status, not an invoice-status field. Extraction bug is gone; the answer shape is still account-centric. |
| C5 weak FAQ | SURPRISE PASS | “tell me something about disputes maybe” did **not** hit FAQ (overlap bar 0.5). DeepSeek wrote an essay on the nature of disputes. Cost **$0.001686**,  lots of output tokens. False-negative FAQ is preferred to false-positive, but this is also how money leaks on vague questions. |

### D — Cache

| ID | Verdict | Observation |
|---|---|---|
| D1 repeat | TRUE PASS | Miss $0.000966 → exact HIT **$0.0**. Old bug (HIT returned stored miss cost) is gone. |
| D2 cross-account | SURPRISE PASS | Same wording, `account_id` 4021/balance 5000 vs 9999/250. Second is **miss**. Answers 5000 vs 250. No leak. Key includes context. |
| D3 HIT logged | SURPRISE PASS | `by_exit.cache >= 1` while tests were in flight; ended at 7. |
| D4 mutate cache off | TRUE PASS | remit pending, cache OFF. |

**Semantic cache actually fired** (not in the suite as a named case): H4’s 20 near-duplicate “triage overdue accounts suite-AH-h4-N” queries produced **5 `cache.semantic` HITs at $0**. Isolation did not block them because context was empty and wording is cosine-close. That is intended for same-tenant paraphrase; it also means H4 was not 20 independent LLM writes.

### E — Compressor & measurement

| ID | Verdict | Observation |
|---|---|---|
| E1 empty context | SURPRISE PASS on the 8200 lie | `tokens_before=2`, `tokens_after=2`, `reduction_pct=0.0`. **Not 8200, not 85.1%.** Then DeepSeek wrote **497 output tokens** on the query `"triage"`. Accounting: cost $0.000988 vs baseline $0.000985 → **saved_pct −0.3%**. CLEVER can **lose** money vs its own baseline when the model is verbose and compression has nothing to cut. |
| E2 identity | SURPRISE PASS | `reduction_pct=0.0`, not 85.1. (Harness printed −1.0 because `0.0 or -1` in Python — ignore that display bug; extra JSON has 0.0.) |
| E3 identity math | TRUE PASS | 66.4% = (0.000357−0.00012)/0.000357. Arithmetic holds. 66.4% here is **cheap vs strong**, not compression. |
| E4 RAS 100% | TRUE PASS on “not hardcoded 8200”; still a **counterfactual** problem | Date query: cost $0, baseline $0.0003 (real tiktoken × strong rate × estimated 150 out tokens), saved_pct 100.0, method `uncompressed_prompt_strong_tier`. Nobody would have called `deepseek-v4-pro` to ask the date. **Do not put RAS 100% in a savings slide.** |

**Baseline undercount:** actual `tokens_in` on E1 was **6** (system/wrapper) vs compressor `tokens_before=2` (query only). That is why empty-context LLM rows go slightly negative. The 8200 costume is dead; a smaller honesty gap remains.

### F — Myelination

| ID | Verdict | Observation |
|---|---|---|
| F1 demo script | SURPRISE PASS on labels | Seeds still `α=50, β=5, n=55`. Script **prints computed** phase/LCB/decision, does not caption “Cerebellar / cheap_ok”. Live math: `p_hat=0.9091`, Wilson LCB=`0.8421` < τ 0.92 → `cheap_ineligible`, phase `warming` (because `.env N_MIN=6`). The demo still does **not** exhibit a cheap-ok cerebellar route. |
| F2 stakes train cheap | SURPRISE PASS | 5× remit pending. `myelination_registry` has **no remit row**. Alpha did not move. Hold path is neutral. |
| F3 cold start | TRUE PASS, **weakened by eval knob** | Fresh `dispute:standard`: phase `cold`, `n_obs=0`, `decision=cold_start`, **strong** called. Suite text said N_min=30. This process has **`N_MIN=6`** in `.env` (comment: so Test-2 could see cheap without 30 paid strong calls). Production default in `gateway/config.py` is still 30. Dashboard `/v1/stats` myelination `phase` also uses a **hardcoded 30**, so it labels `triage:standard n_obs=22` as `cold` even though the live gate already explored cheap. Two different phase functions. |

### G — Security

| ID | Verdict | Observation |
|---|---|---|
| G1 route no key | SURPRISE PASS | 401 `unauthorized`. |
| G2 admin sleep no key | SURPRISE PASS | 401. |
| G3 stats no key | SURPRISE PASS | 401. |
| G4 XSS feature_class | SURPRISE PASS | 422 `unknown feature_class: <img ...>`. Allowlist blocks storage. Dashboard `escapeHtml` on recent/FC panels. Residual: trip-time line still interpolates `t.feature_class` **without** `escapeHtml`. Cannot fire via this vector. Still sloppy. |
| G5 prompt injection | Harness FAIL; **outcome was a refusal** | Query: dump system prompt. Model: “I’m sorry, but I can’t disclose the system prompt…” **No dump.** There is still **no** untrusted-content wrapper in the prompt assembler. One polite DeepSeek refusal is not a control. |
| G6 500 KB | SURPRISE PASS | **413** `payload_too_large` (Content-Length middleware), not a billed call. |
| G7 SQLi | TRUE PASS | `request_log` still exists. Model treated it as an injection attempt in prose. Parameterized SQL. |

Auth is real enough for a laptop demo. **Not** enough for Cvent AR: HTTP not TLS, shared dev key, in-process rate limit, no SSO, no tenant_id. See `SECURITY.md`.

### H — Robustness

| ID | Verdict | Observation |
|---|---|---|
| H1 baseline | TRUE PASS | Trace `request > classifier > stakes_gate > baseline`. Repeat did **not** HIT cache. Two paid strong calls ($0.001244 then $0.000282 — second shorter). |
| H2 unknown class | SURPRISE PASS | 422. |
| H3 empty query | SURPRISE PASS | 422 pydantic min_length. |
| H4 concurrency | TRUE PASS with caveats | Suite-as-written would have cache-collapsed 20 identical queries. Runner **uniquified** `suite-AH-h4-{i}`. 20 HTTP 200. `triage:standard` n_obs 7→22 (**+15**). Cheap_n 1→16. Alpha 2→12, beta 1→6. The missing 5 are **semantic cache HITs** (see model_breakdown), which do not increment n_obs. This is **not** a lost-update wipe; it is cache + quality skipping strong-obs. Concurrent SQL increments landed. |
| H5 3× story | Harness FAIL; **product mostly right** | Miss (pro, −0.2%) → miss (flash, 66.6%) → **exact HIT $0**. First answer almost certainly **failed the quality gate**, so it was not stored; second was stored; third HIT. Dashboard `cache=7`. Original D1/D3 bugs are not what failed. |

---

## 4. Things that are actually working

1. **Provider honesty.** Health and dashboard say `openai_compat`. Usage comes from the vendor response; missing usage would raise, not invent tokens.
2. **Stakes hold** is a control: UUID, no model, cache off, campaign_send included.
3. **Auth** on route/stats/admin. 413 on huge bodies. Feature-class allowlist. Empty query 422.
4. **Exact cache** is isolated by context and bills **$0** on HIT, and the HIT is logged.
5. **Semantic cache** is not vapor: 5 live HITs on paraphrased triage. Isolation held on D2 (different context_hash).
6. **RAS templates** (date, days-until) and **invoice entity** (not year-as-account) work on the synthetic fixture.
7. **Compressor 8200/85.1 costume is dead.** Empty context is 0%.
8. **Pending mutate does not train α.**
9. **SQL stays parameterized** under a DROP TABLE string.

---

## 5. Things that are still wrong, weak, or easy to lie with

1. **`intent_hint` at confidence 1.0 (A4).** Unfixed.
2. **Keyword first-match** steals dunning email into `triage` because `overdue` is listed first (A3).
3. **Dashboard `avg_saved_pct` (59.4%)** still mixes 100% $0 exits. The UI now *warns* (`avg_saved_pct_note`) and shows `llm_saved_pct`. People will still screenshot the big number.
4. **`llm_saved_pct` 32.4 vs dollar-weighted 43.7.** One is the mean of percents (verbose rows go negative); the other is Σsaved/Σbaseline. The dashboard uses the mean. Dollar-weighted is the number that matches the $ columns.
5. **RAS 100%** is arithmetically true and economically fictional for “what is today’s date.”
6. **Baseline ignores wrapper tokens** (`tokens_before` 2 vs billed `tokens_in` 6) → negative save on short prompts + long completions.
7. **Models ramble.** `LLM_MAX_TOKENS=1024` and at least one row billed **2021 completion tokens**. Either the vendor is counting thinking/completion above the cap, or the cap is not binding. That is a cost leak on a 4-word query.
8. **Eval knob `N_MIN=6`.** Cheap flash (13 calls, 66.6% row save) is why LLM savings is not ~0. Production `N_MIN=30` would have kept this suite on strong for most of H4. See savings file.
9. **Dashboard myelin phase ≠ live gate phase** (hardcoded 30 vs settings.N_MIN).
10. **Prompt injection:** no boundary. We got a refusal this time.
11. **C3 4021 vs 40211:** suite vs fixture mismatch. Miss is correct; the paid LLM refusal is the real cost of a bad account parse.
12. **C4** answers account status for an invoice lookup.
13. **Sleep / FAQ promotion** not in A–H. Untested this run.
14. **Not production-ready for real AR data.** HTTP, dev keys, no TLS, no tenant. `SECURITY.md` still NO-GO.

---

## 6. Spend this run (priced, not invoiced)

Harness sum of `accounting.cost_usd`: **$0.02614**.  
Matches `request_log` total. DeepSeek billed usage × off-peak cache-miss table:

| Tier | $/1M in | $/1M out |
|---|---|---|
| flash (cheap) | 0.22 | 0.66 |
| pro (strong) | 0.66 | 1.98 |

13 flash calls = $0.007027. 20 pro = $0.019113. Cache = $0.

Weekend/off-peak was assumed (2026-08-23). Weekday peak would be ~2× on the LLM legs.

**Rotate the DeepSeek key.** It has been pasted in chat in this project’s history.

---

## 7. Myelination leftover after the suite

| route_class | n_obs | α | β | cheap_n (from H4 extra) | dashboard phase (uses 30) |
|---|---|---|---|---|---|
| triage:standard | 22 | 12 | 6 | 16 | cold (misleading) |
| email_draft:standard | 13 | 3 | 4 | — | cold |
| triage:high | 7 | 2 | 1 | 0 | cold |
| dispute:standard | 1 | 1 | 1 | — | cold |

`triage:standard` explored cheap because n_obs was already ≥ 6 before H4 (A2/C3/E1/E2 leftover). That is the eval knob, not a 30-observation cerebellar result.

---

## 8. How to reproduce

```text
# stack already up in this session
cd D:\CLEVER-main\CLEVER-main
python -m harness.run_suite_ah
# then open http://127.0.0.1:8080/  (dashboard)
```

Rate limit is 60/min/key. The runner sleeps 65 s before H4. Do not flush Redis in the middle if you want D1/H5 to mean something; the runner flushes once at start.

H4 uniquification is **intentional** and documented in the runner. Running the suite markdown literally (`for i in 1..20` same body) will **not** test registry races.
