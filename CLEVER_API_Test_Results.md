# CLEVER live API eval (the live API)

**When:** 2026-08-23 (Sunday — vendor off-peak all day per their pricing page)  
**Provider:** `openai_compat` → `https://YOUR_API_BASE_URL`  
**Cheap model id:** `cheap-model`  
**Strong model id:** `strong-model`  
**Thinking:** **disabled** (vendor default is thinking=on; leaving it on would bill chain-of-thought as output and chew the $4.50)  
**Prices used in CLEVER math:** cache-miss **off-peak** from (vendor pricing page)

| Tier | Input / 1M | Output / 1M |
|---|---|---|
| cheap (flash, cache miss, off-peak) | $0.22 | $0.66 |
| strong (pro, cache miss, off-peak) | $0.66 | $1.98 |

Peak weekday cache-miss is 2× those numbers. We did **not** use cache-hit input rates ($0.007 / $0.022). CLEVER does not see the live API's prompt-cache split unless usage reports it.

**Key is in `.env` only. Rotate it.** It was pasted in chat.

**Do not quote dashboard `avg_saved_pct` (71.5%).** That mix still includes older mock rows plus RAS $0.

---

## 1. Scores

| Pass | Result |
|---|---|
| First live API eval | **11/13** — 2 real fails (FAQ stole a dunning email) |
| After FAQ overlap fix + restart | **13/13** |
| FAQ unit tests | **8 passed** (includes new “do not steal dunning email”) |

The 13/13 is after a **bugfix we had to make**. The first run is the honest one for FAQ.

Raw JSON: `harness/last_api_eval.json`  
This-eval accounted USD (CLEVER table, LLM legs only): **~$0.0015**

---

## 2. First run — real fail (not a flaky test)

**Query (clever mode):** “Write a short collections dunning email for this account…”  
**Intended:** call `strong-model` (cold start), draft an email using 40211 / $12,500.  
**Actual:** FAQ HIT. Response was the SLA canned line: *“Standard collections SLA is 30 days…”* Cost **$0**, tokens **0**. No vendor call.

Cause: FAQ scorer required `overlap_frac < τ AND score < τ` to reject. One shared token (“collections”) plus a BM25 bonus cleared the score bar.

**That is a production-class false positive:** a $0 wrong answer instead of a paid email. Flagged, then fixed: overlap fraction **must** be ≥ 0.5. Re-ran.

Vacuous “pass” on the same first run: `clever_in=0 <= baseline_in=72` because clever never called the model. The eval now fails that case if RAS ate the LLM path.

---

## 3. After the FAQ fix — what actually happened

### Still free (no the live API)

| Case | Intended | Actual |
|---|---|---|
| Today’s date | template $0 | PASS |
| Who handles disputes | FAQ $0 | PASS (still hits the real FAQ) |
| Balance 40211 | SQL $12,500 $0 | PASS |
| Remit | pending, no vendor | PASS |

### Paid calls (real usage from the vendor)

**Dunning email, clever (cold start):**

- Model: **`strong-model`** (`forced=true`, `cheap_tried=false` — cold start, correct)
- Provider usage: **40 in / 96 out**, 3275 ms
- CLEVER cost: **$0.000216**
- Compressor: **45.5%** on this small context (not 85% theater)
- Quality: **unchecked_strong** (strong path is still not scored — FLAG)
- Grounding: used **40211** and **$12,500.00**. Did **not** use the contact name Ada (said “Dear Customer”). Partial.

Preview:

> Subject: Urgent: Action Required on Your Account  
> Dear Customer,  
> Our records indicate that account **40211** has an outstanding balance of **$12,500.00** that is now past due.

**Same prompt, `mode=baseline`:**

- Strong, uncompressed: **72 in / 98 out**, **$0.000242**
- Clever input tokens 40 ≤ baseline 72. Savings on this pair: **$0.000026 (~11%)**. That is compression only. Both legs used **pro**. Cheap was never eligible.

**Fat context (4k noise), clever vs baseline:**

- Classifier chose **triage**, so only `account` + `balance` were projected (contact dropped — FLAG)
- Compressor **873→36 (95.9%)** — real, because we stuffed noise
- Clever: **39 in**, **$0.000095**
- Baseline: **1281 in**, **$0.000939**
- Repeat call: **cache HIT, $0**

Fat-pair “90% cheaper” is the noise blob, not a Cvent KPI.

---

## 4. Critical flags (still true)

1. **Cheap model was never used on the live API.** Cold start forces strong. Do not claim flash routing savings until n_obs and LCB ≥ 0.92 (~98/100 cheap successes). That will take real traffic, not this eval.
2. **FAQ was too greedy.** Fixed. Keep the unit test. A $0 wrong answer is worse than a $0.0002 email.
3. **Strong answers are still unscored** (`unchecked_strong`). the live API can be fluent and wrong; we would cache that fluent wrongness for an hour.
4. **Contact name ignored.** Grounding is partial. A collections product should fail quality if `contact` was in context and missing from the letter — we do not.
5. **Fat “summarize account” classified as triage**, so `contact` / `invoice_ids` never reached the model. Classifier is still keyword-cheap.
6. **Dashboard 71.5% avg saved is polluted** (old mock rows + RAS). Ignore it.
7. **Accounted $ ≠ vendor invoice.** We use cache-miss off-peak. If the live API counts cache hits, the card charge is lower. If you run on a weekday peak window, it is ~2×.
8. **Thinking is off.** If someone enables it, output tokens (and cost) can jump an order of magnitude. Keep it disabled for this gateway unless you have a reason.

---

## 5. Go / no-go

**Go:** the live API is wired, usage tokens are real, RAS still costs $0, cache still $0 on repeats, compression is real on fat prompts, stakes still blocks remit.

**No-go:** quoting 71% or 90% savings; claiming cheap-model routing; claiming quality control on strong; treating FAQ as safe without the overlap fix (now in).

**$4.50 budget:** this eval used ~$0.0015 by our table. Plenty left. Do not turn thinking on and loop.

---

## 6. Reproduce

`.env` (never commit):

```
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://YOUR_API_BASE_URL
MODEL_CHEAP=cheap-model
MODEL_STRONG=strong-model
LLM_THINKING=disabled
LLM_API_KEY=  (yours)
```

```
python -m uvicorn gateway.main:app --port 8080
python -m harness.run_api_eval
```

Health must say `"provider": "openai_compat"`. If it says `mock`, stop.

---

*End. Rotate the key that was pasted in chat.*
