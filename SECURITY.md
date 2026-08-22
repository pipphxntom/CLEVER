# CLEVER enterprise security file

**Version:** 0.4.0  
**Date:** 2026-08-23  
**Scope:** gateway + Postgres + Redis as deployed for the challenge (Rancher, local bind).  
**Classification:** internal. Not a SOC 2 report.

This is an engineering audit, not a certification. Residual risk remains.

---

## 1. Current control state (after 0.4.0 patches)

| Control | State | Notes |
|---|---|---|
| AuthN on `/v1/route`, `/v1/stats` | **Present** | `X-API-Key` or Bearer; constant-time compare |
| Admin key on `/v1/admin/*` | **Present** | Separate `CLEVER_ADMIN_KEY` |
| Rate limit | **Present, in-process** | 60/min/key; not shared across workers |
| CORS | **Allowlist** | Not `*` |
| Body size | **Present** | Pydantic + 413 on Content-Length |
| Security headers | **Present on `/v1`** | nosniff, DENY frame, no-store |
| `/docs` | **Off in prod** | `CLEVER_ENV=prod` |
| SQL | **Parameterized** | asyncpg `$1` |
| Redis AUTH + bind | **Present** | `127.0.0.1`, requirepass |
| Postgres bind | **Present** | `127.0.0.1:5432` |
| `.env` gitignored | **Present** | Do not commit keys |
| Confirm tokens | **Single-use Redis** | Mutate path |
| Semantic cache isolation | **context_hash + intent + version** | Prevents cross-account cosine hits |
| Exact cache isolation | **SHA-256 of query+intent+ctx** | |
| Default secrets in prod | **Refused** | Settings validator |
| TLS to clients | **Absent locally** | Challenge laptop HTTP |
| Tenant_id | **Absent** | Single-tenant assumption |
| Disk encryption | **Not specified** | Docker volumes |
| SIEM / request-id in access logs | **Partial** | `request_id` on JSON body only |
| Secret scanning CI | **Absent** | Key was pasted in chat — **rotate** |

---

## 2. Findings (severity)

### High (fixed in 0.4.0 or still operator)

| ID | Issue | Action |
|---|---|---|
| S1 | Semantic cache on query text alone would leak Account A’s letter to Account B | **Fixed:** `context_hash` equality **before** vector search |
| S2 | OpenAPI `/docs` on a collections gateway | **Fixed for prod** (`docs_url=None`). Dev still open behind LAN |
| S3 | API key in chat history | **Operator:** rotate DeepSeek key. Not fixable in code |

### Medium

| ID | Issue | Action |
|---|---|---|
| S4 | HTTP not TLS | Use reverse proxy (Caddy/nginx) at Cvent; local challenge stays HTTP |
| S5 | Rate limit is process-local | OK for one uvicorn worker; not for N workers |
| S6 | `query_text` stored in `semantic_cache` (truncated 500) | PII at rest in Postgres. Restrict DB access; no public port |
| S7 | Dashboard API key in browser field | Dev-only. Do not expose dashboard on a public URL |
| S8 | Health is unauthenticated | Intentional liveness. Does not dump secrets |

### Low

| ID | Issue | Action |
|---|---|---|
| S9 | Default `dev-key-change-me` in `.env.example` | Fine for example; prod start refuses it |
| S10 | In-process APScheduler | One worker only |

---

## 3. Threat model (collections)

Attacker on the same host/network who can hit `:8080`:

- Without key: 401 on route/stats. Health only.
- With stolen route key: can read synthetic aging via RAS; can spend DeepSeek budget; cannot confirm-mutate without the confirm token flow.
- With stolen admin key: can trigger sleep / read FAQ candidates.

Attacker with DB access: full AR snapshot + cached letters. Treat Postgres as confidential.

Prompt injection: user query is concatenated into the LLM prompt. RAS short-circuit reduces exposure for lookups. Generate path still unsandboxed. Do not connect tools/payments to the model.

---

## 4. Operator checklist before any real Cvent data

- [ ] Rotate all keys that appeared in chat
- [ ] `CLEVER_ENV=prod`, non-default API keys, non-default DB password
- [ ] Do not publish 5432/6379 off localhost
- [ ] Do not load production aging Excel
- [ ] Put TLS in front of uvicorn
- [ ] Confirm `SEMANTIC` searches always filter `context_hash`
- [ ] One uvicorn worker or move rate-limit to Redis

---

## 5. Residual risk statement

This is a **challenge / intern-grade gateway** with real auth and isolation patches. It is **not** enterprise-complete (no IdP, no WAF, no vault, no audit SIEM). Shipping Cvent customer AR through it would still be a **NO-GO** until CAI + security review.

---

*End SECURITY.md*
