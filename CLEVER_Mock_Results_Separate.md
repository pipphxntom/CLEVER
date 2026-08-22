# CLEVER mock results — kept separate from API savings

**These numbers are not DeepSeek. Do not mix them into `CLEVER_Final_API_Savings.md`.**

**When:** 2026-08-23  
**Provider:** `mock` (canned completions, tiktoken-sized, priced from whatever `pricing.yaml` was at that moment — originally generic 1.25/2.00, later replaced by DeepSeek list prices)  
**Full write-up:** `CLEVER_Mock_Test_Results.md`  
**Raw:** `harness/last_mock_eval.json`  
**Runner:** `python -m harness.run_mock_eval`  
**Unit tests (no Docker):** `python -m pytest -q` → **48 passed** at the time of that run.

---

## Score (mock HTTP + DB)

| Suite | Result |
|---|---|
| Live mock eval | **30 / 30 pass** (after two *test-design* false fails were removed) |
| First contaminated mock eval | 27/29 — the two fails were unique-query/cache and an LCB-vs-0.90 slide, not product bugs |

Mock can prove plumbing: auth 401, RAS $0 on date/FAQ/SQL, stakes pending + confirm id, compressor 0% on empty context, exact cache HIT $0, cache isolation, baseline mode, myelination LCB arithmetic on seeded α/β.

Mock **cannot** prove: model quality, vendor bills, cheap→strong escalate on a real bad answer, prompt injection, latency, 429s.

---

## Do not quote from mock

| Mock dashboard-ish figure | Why it is not a savings claim |
|---|---|
| avg_saved_pct **73.7%** | Mix of RAS/cache 100% vs a fake-priced mock. |
| Compressor **93.8%** (973→60) | One fixture with a 4k-char `noise_block`. Honest for that payload only. |
| “Cheap_ok / cerebellar” demo | Old script seeds (50/5/55) were ineligible at τ=0.92. Labels were later made honest; the seed still does not unlock cheap. |

---

## What mock got right (and API later confirmed)

- Auth required on `/v1/route` and `/v1/stats`
- Remit / campaign_send pending, no model
- Today’s date $0
- Invoice `INV-2024-089` not account `2024`
- Empty compressor 0%, not 85.1%
- Cache HIT $0 and logged
- Cross-account cache miss
- `mode=baseline` skips optimization

## What mock hid (API found)

- FAQ overlap once **stole a dunning email** on the first live API eval (fixed: overlap ≥ 0.5). Mock never generated that miss.
- Real models **ramble**; empty-context LLM rows can save **negative** percent.
- Semantic cache **did** HIT in Groups A–H (5 times). Mock eval said semantic was unwired at that older revision.
- Cheap routing needs **N_MIN** leftover; mock could seed the registry without paying.

---

## Rule for anyone reading both files

If a percentage came from `LLM_PROVIDER=mock`, it goes in **this** file.  
If it came from DeepSeek `usage` × `pricing.yaml` on Groups A–H, it goes in **`CLEVER_Final_API_Savings.md`**.  
Never average them.
