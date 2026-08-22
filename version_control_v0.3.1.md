# Version control — v0.3.1 (after real_test-1)

**From:** 0.3.0 / real_test-1  
**To:** 0.3.1  
**Why:** Defects measured in real_test-1, not slide polish.

| ID | Change | Files | Why |
|---|---|---|---|
| F1 | Skip FAQ on generate intents | `catalog.py`, `ras_gate.py`, `pipeline.py` | FAQ stole dunning email ($0 wrong answer) |
| F2 | FAQ overlap must be ≥ 0.5 | `ras/faq_match.py` (already in 0.3.0 patch) | Token `collections` bypass |
| F3 | Myelination deadlock: strong increments `n_obs` only; after N_MIN explore cheap for N_EXPLORE trials; then LCB | `myelination.py`, `pipeline.py`, `config.py` | Flash could never run |
| F4 | Score strong outputs; required context fields; do not cache fails | `quality.py`, `cascade.py`, `pipeline.py` | `unchecked_strong` + sticky cache |
| F5 | email_draft keywords (`write a`, `dunning`); triage fields include contact + invoice_ids | `intents.yaml` | Classifier dropped generate / contact |
| F6 | Stats `by_exit`, `short_circuit_pct`, `llm_saved_pct` | `main.py` | One mixed % is dishonest |
| F7 | Dashboard: $0 exit share vs paid $ vs LLM-only %; provider label | `clever_dashboard.html` | Stop telecasting mixed avg as savings |
| F8 | Test-2 eval N_MIN=6, N_EXPLORE=3 in `.env` only | `.env` (gitignored) | Observe cheap explore inside API budget; prod defaults stay 30/10 |

**Not changed:** semantic cache still unwired; sleep still untested; thinking still disabled; DeepSeek prices still cache-miss off-peak.

**Tests added/updated:** classifier write-a, quality required fields, myelination explore.
