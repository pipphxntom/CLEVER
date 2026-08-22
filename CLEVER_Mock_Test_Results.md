# CLEVER mock eval — intended vs actual

**When:** 2026-08-23  
**Stack:** Rancher Desktop (dockerd) + `clever_postgres` + `clever_redis` + gateway `0.3.0`  
**Provider:** `mock` (no external API)  
**Data:** synthetic aging (`40211` / `INV-2024-089`) + 2 FAQ rows  
**Runner:** `python -m harness.run_mock_eval`  
**Raw JSON:** `harness/last_mock_eval.json`  
**Also:** `python -m pytest -q` → 48 passed (unit, no Docker)

**Headline:** Live mock gates that we can actually exercise: **30 / 30 pass.**  
That is **not** “the product is proven.” Mock cannot prove model quality, real token bills, or cascade-on-bad-output. Those stay open until DeepSeek.

Do not quote dashboard `avg_saved_pct` (this run **73.7%**). That mix is mostly $0 short-circuits vs a fake-priced mock, not routing savings.

---

## 1. Score

| Suite | Result |
|---|---|
| Live HTTP + DB eval | **30 pass, 0 fail** |
| Unit tests | **48 pass, 0 fail** |
| First live eval (contaminated) | 27/29 — 2 “fails” were **test bugs**, not product bugs (see §6) |

---

## 2. Gate-by-gate: intended vs actual

Legend: **PASS** = live mock did what the plan said. **OPEN** = plan requires a real model; mock cannot close it. **FLAG** = works, but the number or bar will bite you in API testing.

### Auth / surface

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Health | mock + db + redis ok | `provider=mock`, db ok, redis ok | PASS |
| Stats no key | 401 | 401 | PASS |
| Route no key | 401 | 401 | PASS |
| Dashboard `/` | HTML | 200, title CLEVER | PASS |
| Unknown `feature_class` | 422 | 422 | PASS |

### Pre-LLM short-circuit (RAS)

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Today’s date | template HIT, $0, 0 tokens | HIT `ras.template`, $0, “Today is August 23, 2026.” | PASS |
| Who handles disputes | FAQ HIT, $0 | HIT `ras.faq`, AR team copy | PASS |
| Balance on 40211 | SQL HIT, $12,500 | `Account Northwind Events: balance $12,500.00`, $0 | PASS |
| Status of INV-2024-089 | invoice, **not** account `2024` | HIT structured, `status = open` on Northwind | PASS |

### Stakes

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Remit | pending, no model, confirm id | `pending_confirmation`, tokens_in=0, uuid issued | PASS |
| Launch campaign | pending (`campaign_send`) | intent=`campaign_send`, pending, $0 | PASS |
| Remit + valid token | strong, cache OFF | `tier=strong`, cache `OFF`, tokens_in=8 | PASS |
| Bad token | still pending | pending, tokens_in=0 | PASS |
| Hint `triage` + remit words | mutate wins | pending, intent=`remit` | PASS |

### Compressor / accounting

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Empty context | reduction **0%**, never 85.1 | 8→8 tokens, **0.0%** | PASS |
| Fat unused fields | real drop, noise not in `fields_used` | **973→60 (93.8%)**, fields = YAML list only | PASS |
| RAS baseline | uncompressed prompt at strong tier, **not 8200** | baseline **$0.00091** on a date query | PASS |
| `mode=baseline` | skip RAS/cache/compress, force strong | layers `request > classifier > stakes_gate > baseline` | PASS |

The 93.8% figure is **this fixture** (4k-char noise blob). It is honest for that payload. It is **not** a product KPI.

### Cache

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Second identical call | HIT, $0, tokens 0, logged | HIT, cost 0, `model_used=cache` in `request_log` | PASS |
| Same question, other account | MISS | MISS | PASS |

### Myelination

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Cold start | n&lt;30 → strong, cheap not tried | phase=cold, n_obs=0, `cheap_tried=false`, `forced=true` | PASS |
| Forced-strong does not train | registry stays empty | **0 rows** after many strong drafts | PASS |
| 95% in 100 trials vs floor 0.92 | should **not** unlock cheap | LCB **0.9008** → `cheap_ineligible` | PASS (and FLAG) |
| 98% in 100 trials | should unlock cheap | LCB **0.9413** → `cheap_ok`, `mock-cheap`, no escalate | PASS |

**FLAG:** Quality floor for `collections_outreach` is **0.92**. The old slide “α=95, β=5, LCB 0.907 ≥ 0.90” does **not** unlock cheap anymore. You need about **98/100** cheap successes. That is the real bar.

### Telemetry / stats

| ID | Intended | Actual | Verdict |
|---|---|---|---|
| Intent column | classified, not `unknown` | `unknown_rows=0` | PASS |
| Cache HIT logged | row with $0 | yes | PASS |
| RAS vs stakes columns | split, never both set | `both=0` | PASS |
| Stats window | 24h + separate trip lists | `window=24h`, `short_circuits` vs `stakes_gate_trips` | PASS |

---

## 3. Dashboard numbers this run (do not take these to finance)

From `/v1/stats` after the eval (includes leftover rows from earlier manual clicks):

| Field | Value | Honest reading |
|---|---|---|
| total_requests | 42 | Mix of RAS, stakes, cache, mock LLM |
| total_cost_usd | 0.0071 | Priced from `config/pricing.yaml`, **not a vendor bill** |
| avg_saved_pct | **73.7** | RAS/cache at 100% pull the average up. Empty-context LLM saved **0%**. |
| provider | mock | Badge must stay MOCK |

---

## 4. What mock **cannot** prove (OPEN — fix/watch before DeepSeek)

These are not silent passes. They are **not tested live** or **not meaningful** on mock.

| Item | Why it’s open | Evidence we do have |
|---|---|---|
| Cheap→strong **escalate** on bad output | Mock canned strings are long and pass the heuristic. Live eval never produced `escalated=true`. | Unit test `test_escalate_bills_both_legs` passes. DeepSeek will be the first real escalate. |
| Quality = correctness | Heuristic = refusal regex + length + optional `$` in context. No facts vs aging. | Will misfire on real models (too short / too long / extra dollars). |
| Real USD | `pricing.yaml` is generic (`cheap` 1.25/2.50, `strong` 2.00/6.00). Mock `tokens_*` are tiktoken of canned text. | **Must replace price table with DeepSeek list prices before API eval**, or the $ columns stay fiction. |
| Semantic cache | Still unwired | Table exists, pipeline does not call it |
| Sleep job | Not run in this eval | Code writes FAQ **candidates**, not auto-FAQ. Untested live. |
| Groundedness on real numbers | Mock invents 4021/3887 in canned triage, not from DB | DeepSeek may hallucinate balances — quality may still **pass** |
| Load / timeouts / 429 | Mock is instant | DeepSeek $4.5 is enough for the gold set, not a soak test |

---

## 5. Flags to fix **before** DeepSeek (not optional)

1. **Put DeepSeek prices in `config/pricing.yaml`** (look up current list; do not keep 1.25/2.00). Otherwise “cost_usd” is still a costume.
2. **Do not quote 73.7% or 93.8%.** Report by exit: RAS $0 / cache $0 / LLM actual vs `mode=baseline`.
3. **Cheap unlock is strict.** If DeepSeek cheap fails quality often, you will stay on strong forever. That is correct, and savings will look small. Do not loosen τ to print a slide.
4. **Classifier** labels “what is today’s date” as intent `triage` even though template answers. Harmless for $0; messy in stats buckets.
5. **Mock `email_draft` canned text is only used if the prompt contains the substring `email_draft`.** Real queries say “draft email”, so mock returns the **default** paragraph. Fine for plumbing; DeepSeek will actually draft.

---

## 6. First eval’s two “fails” (closed — were test bugs)

| Apparent fail | Reality |
|---|---|
| `compressor.fat_context_reduces` missing compressor layer | Prior Redis HIT from an earlier manual call with the **same projected fields**. Compressor never ran. Unique query + flush → **973→60, PASS**. |
| `myelination` cheap not used at α=96,β=5,n=100 | LCB 0.9008 **&lt;** τ 0.92. Gate was right. Test expected the old 0.90 slide. |

No product patch required for those two.

---

## 7. Go / no-go for DeepSeek

**Go for a measured API eval**, with the flags in §5 done first (at least pricing.yaml).

**No-go for any savings claim, novelty claim, or “it works in production.”**

Recommended DeepSeek protocol (next session, after you paste the key into `.env` only — not into chat if you can avoid it):

```
LLM_PROVIDER=openai_compat
LLM_API_KEY=...
LLM_BASE_URL=https://api.deepseek.com
MODEL_CHEAP=deepseek-chat
MODEL_STRONG=deepseek-reasoner
```

Then rerun `python -m harness.run_mock_eval` **plus** a gold-set `clever` vs `mode=baseline` table. That table is the only API result that counts.

Anthropic stays a later adapter. Do not point `openai_compat` at Anthropic’s URL; it will fail.

---

## 8. How to reproduce

Rancher Desktop running (dockerd). From repo root:

```powershell
powershell -File scripts\start-stack.ps1
python -m harness.load_aging
python -m uvicorn gateway.main:app --port 8080
python -m harness.run_mock_eval
python -m pytest -q
```

UI: http://127.0.0.1:8080 — API key `dev-key-change-me`. Badge must read MOCK.

---

*End. If a number is not in this file or `last_mock_eval.json`, we did not measure it.*
