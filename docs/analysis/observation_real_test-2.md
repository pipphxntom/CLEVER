# Observation — real_test-2

**Test ID:** `real_test-2`  
**When:** 2026-08-23  
**Build:** v0.3.1 (after real_test-1 defects)  
**Provider:** the live API `openai_compat` (thinking disabled)  
**Eval knobs (not production):** `N_MIN=6`, `N_EXPLORE=3` in `.env`. Production defaults remain 30 / 10.  
**Raw:** `harness/last_real_test2.json`  
**Plots:** `harness/plots/test2_exits.png`, `harness/plots/test2_paid.png`  
**pytest:** 52 passed before this run.

This is a mixed live script: lookups, FAQ, date, two mutate holds, eight **unique** dunning emails, one repeated prompt, one other-account prompt, invoice lookup, triage. Redis and myelination were flushed first. No α/β seeding.

---

## 1. Headline (honest)

v0.3.1 **did** break the cheap-model deadlock: after six strong observations the 7th dunning call entered **`explore`**.

Flash **still never served the user**. On that explore call, cheap failed the quality heuristic (`grounded`), the gateway escalated to **pro** (input tokens **136** ≈ two legs), `beta` jumped by 3, and every later dunning call was **`cheap_ineligible`**.

Final exits in **this script only** (19 requests):

| Exit | Count | Paid? |
|---|---|---|
| ras.structured_lookup | 3 | no |
| ras.faq | 1 | no |
| ras.template | 1 | no |
| stakes_pending | 2 | no |
| llm:strong | 12 | yes |
| llm:cheap | **0** | — |
| cache | **0** | — |

Accounted spend this script: **~$0.00398**. Tier counts: strong 12, cheap 0.

---

## 2. Layer-by-layer

### Short-circuit (working)

- Balance 40211 → SQL, $12,500, $0. Repeat of the same lookup is **SQL again**, not Redis. That is correct: RAS runs **before** cache.
- Disputes → FAQ, AR team, $0. Dunning emails were **not** stolen (generate-intent skip). That is the Test-1 FAQ bug staying dead.
- Date → template, $0.
- Remit / launch campaign → `pending_confirmation`, $0, no vendor.

### Classifier (working for this mix)

- “Write a short collections dunning email…” → `email_draft`.
- “who owes us money…” → `triage`.
- Mutate language still wins.

### Myelination (deadlock gone; explore is too brittle)

| Call | n_obs (before) | decision | Served |
|---|---|---|---|
| draft_0 … draft_5 | 0…5 | cold_start | pro |
| draft_6 | 6 | **explore** | **pro anyway** (cheap fail + escalate, in=136) |
| draft_7, same_a, same_b, other_account | | **cheap_ineligible** | pro |

Why explore died in one shot:

1. Quality `grounded` failed on letters that **did** name Ada, 40211, INV-2024-089, and $12,500 (see previews).
2. Fail reason is currency **format**: model writes `$12,500.00`; context is integer `12500`. Heuristic treats `$12,500.00` as a cited amount not present in context.
3. Score 0.80 < floor 0.92 → fail → no cache → escalate if cheap → `severity=wrong` → **beta += 3**.
4. `cheap_trials` is derived as `(α-1)+(β-1)`, so one fail counts as **three** trials. `N_EXPLORE=3` is exhausted immediately. LCB on 0/3 ≈ 0 → lockout.

This is a **real remaining bug**, not “flash is bad.” The model was grounded in English and the gate said no.

### Cache (did not fire on the intended repeat)

`draft_same_a` and `draft_same_b` used the **same** query+context. Both paid. Because quality `passed=false`, pipeline **does not write cache**. That is consistent with “don’t cache bad letters,” but here the letters were not actually bad — the heuristic was.

Other-account (`38870` / Lee Park) correctly did not share 40211’s answer (both misses anyway).

### Quality on strong (now on; too strict on money format)

`method=heuristic_strong`, `checked=true`, **every** dunning letter `passed=false` for `grounded`. We are no longer rubber-stamping strong. We are failing good output. Floor 0.92 + 0.2 grounded deduction = 0.80 fail.

### Compression / $ on paid drafts

Saved_pct on unique dunning **1.3–1.8%**. Context is already small. That is honest. Fat-junk 90% from Test-1 is not this mix.

### Dashboard 24h (do not screenshot as Test-2)

`/v1/stats` is a **24h window including Test-1 + mock leftovers**: 79 rows, mixed `avg_saved_pct` 63.9 (labeled MIXED), `short_circuit_pct` 55.7, `llm_saved_pct` 18.4, `by_exit` ras 25 / cache 6 / stakes 13 / llm 35.

The **script’s own** 19 rows are the Test-2 truth. The 24h average is not.

---

## 3. Plots

- `harness/plots/test2_exits.png` — exit counts for the 19-call script.  
- `harness/plots/test2_paid.png` — CLEVER-table $ for paid calls only.

If a judge asks “did cheap win?” the exit chart says **no**.

---

## 4. Claims vs Test-2

| Claim | Test-2 |
|---|---|
| Pre-LLM filter | Holds on lookup/FAQ/date. Generate no longer FAQ-stolen. |
| Human confirm | Holds. |
| Exact cache | **Not demonstrated** here (quality fail blocked store). |
| Cheap routing | Explore **attempted once**, then locked. **0 cheap finals.** |
| 70%+ savings | **False** for generation (~2%). $0 share is lookups+holds, not routing. |
| Quality protects users | Intent good, implementation **rejects valid $12,500.00 vs 12500**. |

---

## 5. What is still broken after v0.3.1

1. **Money-format grounded check** — `$12,500.00` vs `12500` fails. Blocks cache and cheap.  
2. **Explore counting** — `beta += 3` counts as three explore trials. One fail ends `N_EXPLORE=3`.  
3. **Cheap never served** a final answer in Test-2.  
4. **24h stats** still mix historical runs. Need a `?window=` or test-id, or flush `request_log` for a clean dashboard (flushing prod logs is a product choice).  
5. Semantic cache / sleep still unused.

---

## 6. Next fix (if we continue)

Normalize amounts to digit strings before grounded compare (12500 in 1250000? use integer dollars). Count explore **calls** as +1 regardless of β weight. Then re-run a short Test-3 of five unique emails + one repeat.

Until then: **do not claim cheap routing or cache on this mix.** The $0 path for lookups and the remit hold are the only challenge-safe wins.

---

*End observation_real_test-2. Eval N_MIN=6 is not a production setting.*
