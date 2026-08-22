# CLEVER — final handoff (load this on another machine)

**Product:** CLEVER, a FastAPI gateway that sits between an app and an OpenAI-compatible LLM. It classifies intent, holds mutations for a confirm token, tries regex/SQL/FAQ before the model (RAS), compresses context, caches (exact + MiniLM semantic), optionally routes cheap vs strong after enough observations, and logs cost vs a strong-tier baseline.

**Version this packet describes:** `0.4.0`  
**Code root:** `CLEVER-main/` (if you cloned a zip you may have `CLEVER-main/CLEVER-main/` — **run commands from the directory that contains `gateway/` and `infra/`**).

**This is a laptop challenge build.** It is not a Cvent production service. No TLS, no SSO, no tenant isolation. Read `SECURITY.md` before pointing it at real AR data. Verdict there is still **NO-GO** for real customer data.

---

## 1. What to read, in order

| File | Why |
|---|---|
| **This file** | Install, run, where the truth is. |
| `CLEVER_Suite_AH_Observation.md` | Groups A–H live DeepSeek, case by case, including failures. |
| `CLEVER_Final_API_Savings.md` | The only savings percentages that use a real model. |
| `CLEVER_Mock_Results_Separate.md` | Mock-only; do not mix into API %. |
| `SECURITY.md` | What is gated and what is not. |
| `CLEVER_Novels_Status.md` | RAS / myelination / sleep — what is science vs filter. |
| `version_control_v0.4.0.md` | What changed vs 0.3.1. |
| `CLEVER_Test_Suite.md` | The A–H script that was executed. |
| `CLEVER_Hardproof_Analysis.md` | Original audit (many traps are now fixed; some are not). |

Raw JSON from the A–H run: `harness/last_suite_ah.json`.  
Do **not** treat `archive/glean_generators/` as source — `DO_NOT_RUN.txt`.

---

## 2. Machine requirements

| Piece | Requirement |
|---|---|
| OS | Windows was used. Linux/macOS should work if you translate the `.ps1` to compose up. |
| Python | 3.11+ (this run was **3.13**). |
| Container engine | **Rancher Desktop, container engine = dockerd (moby).** Cvent-supported. **Not Docker Desktop** — it steals the `docker` context (`desktop-linux`) and this repo’s scripts will refuse it. |
| RAM | 8 GB+ . First start downloads `pgvector` + Redis + **sentence-transformers MiniLM** (~80 MB) into the Python env. |
| Network | DeepSeek API if you want live LLM. Mock mode works offline after images/pip are cached. |

Install Rancher if needed:

```powershell
winget install -e --id SUSE.RancherDesktop
```

Then: Rancher Desktop → Preferences → Container Engine → **dockerd (moby)**. Quit Docker Desktop if it is installed. Wait until Rancher shows **Running**.

---

## 3. Install

```powershell
cd <the folder that contains gateway, infra, scripts>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy env:

```powershell
copy .env.example .env
```

Edit `.env`:

```env
CLEVER_ENV=dev
CLEVER_API_KEY=dev-key-change-me
CLEVER_ADMIN_KEY=dev-admin-change-me

# Offline / unit / mock eval:
LLM_PROVIDER=mock

# Live DeepSeek (this packet’s A–H run):
# LLM_PROVIDER=openai_compat
# LLM_API_KEY=<your key — never commit>
# LLM_BASE_URL=https://api.deepseek.com
# MODEL_CHEAP=deepseek-v4-flash
# MODEL_STRONG=deepseek-v4-pro
# LLM_THINKING=disabled
# LLM_TIMEOUT_S=90
# LLM_MAX_TOKENS=1024

POSTGRES_DSN=postgresql://clever:clever@localhost:5432/clever
REDIS_URL=redis://:clever@localhost:6379/0
```

**Production knobs** (in `gateway/config.py` defaults): `N_MIN=30`, `N_EXPLORE=10`.  
The A–H machine had `N_MIN=6` and `N_EXPLORE=3` in `.env` so cheap routing was observable without 30 paid strong calls. **If you want to reproduce the 43.7% LLM save, you need those eval knobs. If you want production behavior, delete them.** Savings file explains the difference (~14% estimated without the knob).

Rotate any key that has been in chat history.

---

## 4. Start Postgres + Redis (Rancher)

```powershell
powershell -File scripts\start-stack.ps1
```

That script:

1. Refuses Docker Desktop.
2. `docker compose -p clever -f infra\docker-compose.yml up -d`
3. Applies `db/schema.sql`, `schema_novel.sql`, `schema_v03.sql`, **`schema_v04.sql`** (cheap_n + 384-d semantic vectors).
4. Seeds FAQ (`harness/seed_faq.sql`).

Compose binds Postgres **127.0.0.1:5432** and Redis **127.0.0.1:6379** with password `clever`. Redis requires AUTH (`REDIS_URL` already has it).

Load the **synthetic** aging fixture (two accounts: `40211` / `38870`, invoice `INV-2024-089`):

```powershell
python -m harness.load_aging
```

Do not point `load_aging` at production files.

---

## 5. Start the gateway

From the code root, with the venv active:

```powershell
python -m uvicorn gateway.main:app --port 8080
```

Check:

```powershell
curl -s http://127.0.0.1:8080/health
```

You want `"status":"ok"`, `"db":"ok"`, `"redis":"ok"`, and `"provider"` equal to what you set (`mock` or `openai_compat`). If `provider` is wrong, you are looking at a stale process on 8080.

**Dashboard:** open `http://127.0.0.1:8080/`  
The API key field is pre-filled with `dev-key-change-me`. Stats polling needs that header. After a live A–H run the KPIs should match §6.

Smoke route (mock or API):

```powershell
curl -s -X POST http://127.0.0.1:8080/v1/route `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-key-change-me" `
  -d "{\"query\":\"what is today's date\"}"
```

Expect `ras.template` HIT, `cost_usd` 0.

Without the header: **401**. That is correct.

---

## 6. Reproduce the tests in this packet

Unit (no Docker):

```powershell
python -m pytest -q
```

Mock live eval (gateway must be `LLM_PROVIDER=mock`, stack up):

```powershell
python -m harness.run_mock_eval
```

Groups A–H against **live** DeepSeek (gateway must be `openai_compat`, key in `.env`, stack up). **Spends money** (this run was **~$0.026** off-peak):

```powershell
python -m harness.run_suite_ah
```

The suite runner:

- Snapshots `/v1/stats` to `harness/pre_suite_ah_stats.json`
- **Deletes `request_log`** so the dashboard 24h window is the suite (aging/FAQ/myelination kept)
- Flushes Redis once so cache tests are clean
- Sleeps 65 s before 20 concurrent calls (rate limit is 60/min/key)
- Uniquifies H4 queries (the markdown’s identical loop cannot test a registry race)

Output: `harness/last_suite_ah.json`.

Other harnesses: `run_api_eval.py`, `run_real_test2.py`, `run_ab.py` — older; they may flush Redis/myelination.

---

## 7. Dashboard numbers from the A–H run (already executed)

If you start a **fresh** DB you will **not** see these until you re-run the suite.

| Field | Value |
|---|---|
| provider | openai_compat |
| total_requests | 55 |
| total_cost_usd | 0.0261 |
| avg_saved_pct | 59.4 — **do not quote** |
| llm_saved_pct | 32.4 (mean of percents) |
| short_circuit_pct | 40.0 |
| by_exit | ras 4, cache 7, stakes 11, llm 33 |
| models | pro 20, flash 13, semantic cache 5, exact cache 2 |

Quote savings from `CLEVER_Final_API_Savings.md`: **43.7% LLM dollar-weighted** on this run, **~14% estimated** at production `N_MIN=30`.

---

## 8. Layout (what you are loading)

```
gateway/main.py          FastAPI: /health / /v1/route /v1/stats /v1/admin/*
gateway/pipeline.py      15-step route
gateway/auth.py          X-API-Key / admin key
gateway/layers/*         classifier, stakes, RAS, cache, semantic, compressor, cascade, quality, myelination
gateway/providers/       mock + openai_compat
config/*.yaml            intents, features, pricing, vpt
db/schema*.sql           apply in order through v04
infra/docker-compose.yml Rancher postgres+redis
superblocks/clever_dashboard.html  served at /
harness/                 eval runners + fixtures
tests/                   pytest
scripts/start-stack.ps1  Rancher bring-up
```

---

## 9. Known holes the next owner should not “fix” by loosening bars

1. **`intent_hint` still trusted at conf 1.0** for known non-mutate intents (A4).
2. **Keyword first-match** classifies “dunning email … overdue” as `triage`.
3. **Do not raise `avg_saved_pct` by counting RAS 100%.** The dashboard already warns.
4. **Do not lower `N_MIN` or τ** to print a cheap-routing slide. τ for `collections_outreach` is 0.92.
5. **Prompt assembly has no untrusted boundary.** G5 was a model refusal, not a control.
6. **No TLS / SSO / tenant.** Laptop only.
7. **`start-stack.ps1` now applies `schema_v04.sql`.** Older copies of the script skipped it; semantic 384-d and `cheap_n` would then be wrong.
8. Sleep/FAQ promotion exists as code; A–H did not prove it.

---

## 10. Secrets

- `.env` is gitignored. Never commit it.
- Default keys `dev-key-change-me` / `dev-admin-change-me` are **dev only**. `CLEVER_ENV=prod` refuses them.
- DeepSeek key used for A–H was in `.env` and **also appeared in prior chat — rotate it.**
- This handoff does **not** contain API keys.

---

## 11. If something does not start

| Symptom | Likely cause |
|---|---|
| `start-stack` errors on `desktop-linux` | Docker Desktop context. `docker context use rancher-desktop` or uninstall Desktop. |
| health `db: error` | Compose not up, or DSN password mismatch. |
| health `redis: error` | Redis requirepass; URL must be `redis://:clever@localhost:6379/0`. |
| `/v1/route` 401 | Missing `X-API-Key`. |
| `/v1/route` 422 unknown feature_class | Allowlist in `config/features.yaml`. |
| 503 upstream_error | Provider timeout / bad key / thinking tokens. Check gateway stdout. |
| MiniLM slow first request | `sentence-transformers` download. Wait; do not assume hang. |
| Dashboard empty KPIs | Stats need the key in the top field; or `request_log` empty. |
| `provider: mock` during an “API” test | `.env` not loaded or wrong cwd when starting uvicorn. |

---

## 12. Honest status for the person inheriting this

CLEVER **does** intercept calls, hold mutations, answer a few lookups at $0, cache with isolation, measure tokens with tiktoken, and bill from vendor usage × a real price table. Groups A–H on DeepSeek did **not** crash. The old 85.1% / 8200-token / confirm-theater / unauthenticated-route defects are **gone**.

CLEVER does **not** deliver an 80–95% production savings number. Live A–H LLM dollar-weighted save was **43.7%** under an eval `N_MIN=6`, and would have been **~14%** on the same traffic with production `N_MIN=30`. Short-circuiting 40% of *this* suite (lots of remit holds and date templates) is not the same as 40% of Cvent production traffic.

Load it, run health, run pytest, then decide whether you are in **mock** or **openai_compat**. Do not screenshot `avg_saved_pct`.
