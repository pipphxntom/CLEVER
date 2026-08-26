# CLEVER “novels” — honest status (2026-08-23)

These are product mechanisms with neuroscience names. They are **not** published scientific results. Prior art: FrugalGPT (2023), RouteLLM (2024), FAQ/rules gateways, Beta-Bernoulli tracking.

| Mechanism | Intended | Live evidence | Verdict |
|---|---|---|---|
| **RAS (pre-LLM short-circuit)** | SQL + FAQ + templates before any model | Date, disputes FAQ, 40211 balance all **$0** on HTTP API runs. FAQ **stole a dunning email** once; generate intents now skip FAQ. | **Working as a filter.** Not “RAS” science. False-positive was a real bug; patched. |
| **Myelination (Beta + Thompson routing)** | Unlock cheap after evidence | Cold-start deadlock **was real**. **v0.5.0** live HTTP API probe (`harness/last_routing_sleep_api.json`): seeded explore + lock-in both produced **flash finals** (quality 1.0, no escalate). Lock-out stayed strong. Pass 1 explore was stolen by **semantic cache HIT 0.930** — Redis flush is not enough. Organic cold→lock-in **not** shown. Process still had **`N_MIN=6`**. | **Mechanism works when the request reaches it.** Not a production savings result. Full write-up: `CLEVER_v0.5.0_Routing_Sleep_Evaluation.md`. |
| **Exact cache** | Repeat → $0 | Worked when quality passed. Test-2: quality fail → **no store** → repeat paid. Isolation (other account) designed correctly. | **Correct when quality passes.** Test-2 did not demonstrate HIT. |
| **Semantic cache** | Fuzzy same-account repeats | **Wired in 0.4.0** with `context_hash` isolation + MiniLM 384-d. Not in Test-1/2 numbers until next run. | **Code complete; not yet measured live.** Cross-account cosine without hash would have been a leak — we refused that design. |
| **Sleep consolidation** | Periodic prune / FAQ candidates / posterior decay | v0.5.0 live: manual `/v1/admin/consolidate` decayed 51,3→41,3→33,3, queued a quality-gated **candidate**, did **not** auto-publish FAQ, wrote `consolidation_log`. Redis exact-key extend **not implemented** (hashes do not match). **Not** a week of unattended traffic. | **Maintenance job. Manual trigger works.** Not novel. Auto-FAQ would reintroduce RAS steal. |
| **VpT / TCR** | Finance story | Formula runs. YAML dollars are **assumed**. TCR on mock mix is not a governance metric. | **Accounting garnish.** Do not take to finance. |
| **80–95% savings** | Business goal | Real dunning vs baseline **~11%** (both pro). $0 on lookups. Mixed dashboard % is **not** that goal. | **Claim false as stated.** |

**Positive:** The useful CLEVER idea (don’t pay for lookups; hold mutate; compress; cache exact) is real and measured.

**Negative:** Branding as novel RAS/myelin/sleep is a liability. v0.5 seeded live drafts **did** keep cheap finals; that is not organic lock-in and not a production %. Quality/cache still hide the layer under test (Test-2 exact cache; v0.5 semantic cache).

---

*If a judge asks “is the science new?” the answer is no. If they ask “does the gateway skip the LLM for a balance lookup?” the answer is yes.*
