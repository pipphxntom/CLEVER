# Version control — v0.4.0

| ID | Change |
|---|---|
| Q1 | Money grounding: `$12,500.00` == context `12500` |
| Q2 | Explore: `cheap_n += 1` per cheap trial (not beta+=3 as 3 trials) |
| C1 | Semantic cache: MiniLM 384-d, `context_hash` isolation, TTL, quality-gated write |
| C2 | Exact cache unchanged isolation; writes only if quality passed (now passable) |
| C3 | Embed in `asyncio.to_thread` (first version blocked the event loop → 120s timeout) |
| AB | `harness/run_ab.py` clever vs baseline |
| S1 | Security headers + 413; prod refuses default Redis password |
| S2 | `SECURITY.md`, `CLEVER_Novels_Status.md` |
| DB | `db/schema_v04.sql` |

A/B (live DeepSeek, 2026-08-23): RAS questions $0 clever vs paid baseline; dunning clever **cheap $0.000136** vs baseline **strong $0.000310**.
