# CLEVER starter — clone to “it works on my machine”

**Short path:** `RUN.md` + `powershell -File scripts\first-run.ps1`

**Audience:** you just cloned the repo. You have not run it before.  
**Default mode in this file:** **mock LLM** (no API key, no spend). That is enough to prove the gateway, dashboard, RAS, stakes, cache plumbing, and health.  
**OS these commands were written for:** Windows PowerShell. Linux/macOS notes at the bottom.

This is a **laptop challenge build**. No TLS, no SSO. Do not point it at real customer AR data. Read `SECURITY.md` if you might.

---

## 0. Find the code root

Commands must run from the folder that contains **`gateway/`**, **`infra/`**, **`scripts/`**, and **`requirements.txt`**.

If you cloned a zip you may have `CLEVER-main/CLEVER-main/`. Go one level in until you see `gateway`.

```powershell
cd <the folder that contains gateway, infra, scripts>
dir gateway, infra, scripts, requirements.txt
```

If those four are missing, you are in the wrong directory.

---

## 1. What you need installed

| Piece | Default |
|---|---|
| Python | 3.11+ (`python --version`) |
| Rancher Desktop | Container engine = **dockerd (moby)**. **Not Docker Desktop** — this repo’s start script will refuse `desktop-linux`. |
| RAM | 8 GB+. First start downloads Postgres pgvector, Redis, and MiniLM (~80 MB) into the venv. |

If Rancher is missing:

```powershell
winget install -e --id SUSE.RancherDesktop
```

Then: open **Rancher Desktop** → Preferences → Container Engine → **dockerd (moby)**. Quit Docker Desktop if it is installed. Wait until Rancher shows **Running**.

---

## 2. Virtual environment (do this)

From the code root:

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Your prompt should show `(.venv)`. If `Activate.ps1` is blocked, the `Set-ExecutionPolicy` line is only for **this** PowerShell window.

Unit tests (no Docker, no gateway):

```powershell
python -m pytest -q
```

You want tests passing (currently 73). If this fails, stop — the venv or install is wrong.

---

## 3. Env file (default = mock)

```powershell
copy .env.example .env
```

Do **not** edit it for the default walkthrough. `.env.example` already has:

- `LLM_PROVIDER=mock`
- `CLEVER_API_KEY=dev-key-change-me`
- `CLEVER_ADMIN_KEY=dev-admin-change-me`
- Postgres / Redis URLs for the local compose stack

**Do not commit `.env`.** Do not paste a live LLM key unless you intend to spend money (optional §8).

Do **not** add `N_MIN=6` unless you are deliberately reproducing the old eval-knob savings slide. Production default in code is `N_MIN=30`.

---

## 4. Start Postgres + Redis + schema

Rancher must be **Running**. Then:

```powershell
powershell -File scripts\start-stack.ps1
```

That script: refuses Docker Desktop, starts `clever_postgres` + `clever_redis`, applies `schema.sql` through **`schema_v05.sql`**, seeds FAQ.

Load the **synthetic** aging file (two fake accounts: `40211`, `38870`):

```powershell
python -m harness.load_aging
```

Do not point that at a production spreadsheet.

Quick check:

```powershell
docker ps --format "{{.Names}} {{.Status}}"
```

You want `clever_postgres` and `clever_redis` **healthy**.

---

## 5. Start the gateway

Keep the venv active. **Leave this window open.**

```powershell
python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8080
```

Wait until you see: `Application startup complete` and `Uvicorn running on http://127.0.0.1:8080`.

First boot may sit on MiniLM download. That is not a hang.

Optional second terminal (activate `.venv` again) for all `curl` / `python -m harness...` commands below.

---

## 6. Open these in the browser

| URL | What it is | What “good” looks like |
|---|---|---|
| **http://127.0.0.1:8080/health** | JSON health | `"status":"ok"`, `"version":"0.5.0"`, `"provider":"mock"`, `"db":"ok"`, `"redis":"ok"` |
| **http://127.0.0.1:8080/** | **Dashboard** (this is the UI to watch) | Dark “CLEVER — AI Cost Intelligence Dashboard”. API key field should already be `dev-key-change-me`. After a few `/v1/route` calls, KPIs / recent requests populate. |
| **http://127.0.0.1:8080/docs** | Swagger (dev only) | Try `POST /v1/route` here if you prefer a form. You must click **Authorize** and enter `dev-key-change-me` (header `X-API-Key`). |

If `/health` shows `"provider":"openai_compat"` you are **not** in the default mock setup — wrong `.env` or a leftover process on 8080.

**Dashboard note:** the top key field is required for `/v1/stats` polling. Empty KPIs on a fresh DB are normal until you send routes. **Do not screenshot `avg_saved_pct`** as a product number — the UI itself says that mix includes RAS/cache 100%.

Nothing else to open. Postgres/Redis have no web UI in this repo.

---

## 7. Commands that prove the pipeline (copy these)

Same machine, venv on, gateway still running.

**7.1 No key → 401 (auth is on)**

```powershell
curl.exe -s -o NUL -w "%{http_code}" -X POST http://127.0.0.1:8080/v1/route -H "Content-Type: application/json" -d "{\"query\":\"hello\"}"
```

Expect: `401`

**7.2 Date lookup → RAS, $0, no model**

```powershell
curl.exe -s -X POST http://127.0.0.1:8080/v1/route `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-key-change-me" `
  -d "{\"query\":\"what is today's date\"}"
```

Expect: `"status":"ok"`, `"cost_usd":0.0`, `"tokens_in":0`, a `ras.template` HIT in `decision_trace`. Refresh the dashboard — you should see a $0 RAS row.

**7.3 Remit → hold, no model**

```powershell
curl.exe -s -X POST http://127.0.0.1:8080/v1/route `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-key-change-me" `
  -d "{\"query\":\"please remit payment for 40211\"}"
```

Expect: `"status":"pending_confirmation"` and a `confirmation_id`. No LLM tokens.

**7.4 Structured balance (needs aging loaded)**

```powershell
curl.exe -s -X POST http://127.0.0.1:8080/v1/route `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-key-change-me" `
  -d "{\"query\":\"what is the balance on account 40211\",\"context\":{\"aging_version\":\"synthetic-v1\"}}"
```

Expect: cost `0`, RAS structured lookup, balance **12,500** / Northwind in the text.

**7.5 Sleep job (admin key, not the API key)**

```powershell
curl.exe -s -X POST http://127.0.0.1:8080/v1/admin/consolidate `
  -H "X-API-Key: dev-admin-change-me"
```

Expect: `"status":"ok"` and a `job_id`. On a fresh DB `decayed` / `candidates` may be **0**. That is still success — the job ran. `"status":"skipped_lock"` is a fail (lock stuck).

**Default walkthrough is done** if 7.1–7.5 plus `/health` and the dashboard match the table in §6.

---

## 8. Optional: live LLM (spends money)

Both backends can be live at once (`LLM_PROVIDER=auto`).

- **HTTP API:** `LLM_API_KEY` + `LLM_BASE_URL` + `COMPAT_MODEL_*`
- **Bedrock:** `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_SESSION_TOKEN` (if STS) + `BEDROCK_MODEL_*`

See `WHAT_TO_PROVIDE.md` and `RUN.md`. Restart uvicorn after filling `.env`. `/health` must show the backend you intended (`openai_compat`, `bedrock`, or `mock`). A stale process on 8080 is the usual mix-up.

`config/pricing.yaml` must match the models you configured. Wrong table = dishonest dollar columns.

Do not mix HTTP-API eval savings with Bedrock eval savings.

---

## 9. If it does not start

| Symptom | Likely cause |
|---|---|
| `start-stack` / `desktop-linux` | Docker Desktop stole the CLI. Quit it. Rancher = dockerd. |
| `rdctl` / engine not ready | Rancher still booting. Wait until **Running**. |
| health `db: error` | Compose down, or DSN not `clever:clever`. |
| health `redis: error` | URL must be `redis://:clever@localhost:6379/0` (password in the URL). |
| `/v1/route` 401 | Missing `X-API-Key`. |
| 503 `upstream_error` | Live provider timeout / bad key. Check the uvicorn window. |
| Dashboard empty | Fresh DB, or key field blank. Send §7 routes, wait ~5s. |
| `Activate.ps1` disabled | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Nested folder | You ran commands from the outer `CLEVER-main` zip wrapper. |

---

## 10. What to read after it boots

| File | Why |
|---|---|
| `CLEVER_STARTER.md` | This file. |
| `CLEVER_v0.5.0_Routing_Sleep_Evaluation.md` | Honest pass/fail of Thompson routing + sleep. |
| `CLEVER_Final_API_Savings.md` | Only live dollar-weighted % (v0.4.0 A–H, `N_MIN=6` caveat). |
| `CLEVER_Novels_Status.md` | What is a filter vs a slogan. |
| `SECURITY.md` | NO-GO for real customer data. |

Do **not** run anything under `archive/glean_generators/` (`DO_NOT_RUN.txt`).

---

## Linux / macOS (same idea, translate the shell)

```bash
cd <folder with gateway and infra>
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# start Rancher/docker equivalently, then:
docker compose -p clever -f infra/docker-compose.yml up -d
# apply db/schema.sql … schema_v05.sql and harness/seed_faq.sql the same order as scripts/start-stack.ps1
python -m harness.load_aging
python -m uvicorn gateway.main:app --host 127.0.0.1 --port 8080
```

Browser URLs in §6 are unchanged.
