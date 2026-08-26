# Real Test Result-1 — versioned record

**Test ID:** `real_test-1`  
**Status:** CLOSED (baseline before v0.3.1 fixes)  
**Date:** 2026-08-23  
**Build:** CLEVER gateway 0.3.0  
**Engine:** Rancher Desktop dockerd (not Docker Desktop)  
**Provider after switch:** `openai_compat` @ `https://YOUR_API_BASE_URL`  
**Models:** cheap=`cheap-model` · strong=`strong-model`  
**Thinking:** disabled  
**Pricing file:** `config/pricing.yaml` cache-miss off-peak (Sunday)  
**Artifacts:**  
- `harness/last_mock_eval.json`  
- `harness/last_api_eval.json`  
- `CLEVER_Mock_Test_Results.md`  
- `CLEVER_API_Test_Results.md`  
- `observation_real_test-1.md`

This file is the frozen record of what we measured **before** the v0.3.1 defect fixes. Do not edit numbers after the fact.

---

## 1. Environment

| Item | Value |
|---|---|
| Postgres / Redis | `clever_postgres`, `clever_redis` healthy, bound 127.0.0.1 |
| Aging | synthetic 2 rows (40211 / INV-2024-089) |
| FAQ | 2 rows (SLA, disputes) |
| Auth | `X-API-Key` required |
| Eval spend (API table) | ~$0.0015 |

---

## 2. Scores

| Suite | Score | Note |
|---|---|---|
| pytest (unit) | 48/48 then FAQ 8/8 | Isolated logic |
| Live mock eval | 30/30 | After flushing Redis and unique queries |
| Live the live API **first** | **11/13 FAIL** | FAQ stole dunning email |
| Live the live API **after FAQ overlap patch** | 13/13 | Still no cheap-model calls |

---

## 3. Case log (the live API, post-overlap-patch — last_api_eval.json)

| ID | Intended | Actual | Pass |
|---|---|---|---|
| health.not_mock | openai_compat | ok | Y |
| ras.date | template $0 | Today is August 23, 2026. $0 | Y |
| ras.faq | disputes FAQ $0 | AR team $0 | Y |
| ras.structured | balance 40211 | Northwind $12,500 $0 | Y |
| stakes.pending | remit no vendor | pending, tok=0 | Y |
| llm.clever_draft | real model email | **pro** 40 in / 96 out / $0.000216 / 3275 ms / cold_start | Y |
| llm.clever_draft.grounding | 40211 or $12500 or Ada or INV | 40211 and $12,500; **not Ada** | Y (weak bar) |
| llm.baseline_draft | uncompressed strong | 72 in / 98 out / $0.000242 | Y |
| clever vs baseline tokens | clever_in ≤ baseline_in, not RAS | 40 ≤ 72 | Y |
| fat compress | noise dropped | 873→36 (95.9%), fields account+balance only | Y |
| fat cheaper | clever ≤ baseline $ | $0.000095 vs $0.000939 | Y |
| cache repeat | HIT $0 | HIT | Y |
| stats.provider | openai_compat | yes; avg_saved_pct 71.5 **polluted** | Y (provider only) |

---

## 4. First API run failure (must stay in the record)

Query: “Write a short collections dunning email…”  
Returned: SLA FAQ (“30 days from invoice due date”), $0, no model.  
Cause: FAQ score `frac < τ AND score < τ` let token `collections` through.  
Class: **false $0 answer**. Fixed later as overlap ≥ 0.5. This result-1 includes the failure.

---

## 5. Paid the live API numbers (honest)

| Call | Model | in | out | CLEVER $ | Notes |
|---|---|---|---|---|---|
| Dunning clever | strong-model | 40 | 96 | 0.000216 | Forced strong, 45.5% compress |
| Dunning baseline | strong-model | 72 | 98 | 0.000242 | Same prompt uncompressed |
| **Delta** | | | | **$0.000026 (~11%)** | Compression only. **Flash unused.** |
| Fat clever | pro (cold) | 39 | — | 0.000095 | Triage fields only |
| Fat baseline | pro | 1281 | — | 0.000939 | Noise in prompt |
| Fat repeat | cache | 0 | 0 | 0 | HIT |

---

## 6. Claims check (result-1)

| Claim | Result-1 verdict |
|---|---|
| 85.1% compression always | **False.** Empty 0%. Real email 45.5%. Fat junk 95.9%. |
| 93.9% cost save | **False.** Real pair ~11%. Dashboard 71.5% is mix + old rows. |
| Pre-LLM filter | Works for date/FAQ/lookup on gold set. Failed on generate-vs-FAQ. |
| Human confirm | Works as hold. |
| Cheap routing | **Not observed.** Deadlock: cold start never trains cheap. |
| Quality | Strong unchecked. |
| Novel | Not evidenced. |

---

## 7. Defects frozen at result-1 (inputs to v0.3.1)

1. FAQ can steal generate intents.  
2. Myelination deadlock: strong-only never increments cheap trials → flash never runs.  
3. Strong output not quality-checked; cache can store fluent wrong letters.  
4. Grounding does not require contact / invoice.  
5. Classifier maps summarize/draft poorly; triage drops contact.  
6. Stats one-number `avg_saved_pct` mixes RAS 100% with LLM.  
7. Dashboard telecasts that mixed average as “Avg Savings.”  
8. Semantic cache unwired. Sleep untested. Escalate unproven on API.

---

*Version: real_test-1 / 2026-08-23 / do not rewrite history.*
