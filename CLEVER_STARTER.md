# CLEVER starter — clone to running

This is the file to follow after `git clone`. It matches the current tree (gateway `0.6.0`).  
Laptop demo only: HTTP, no TLS, no SSO. Do not point it at real customer data. See `SECURITY.md`.

---

## 0. Where to run commands

You must be in the folder that contains **`gateway/`**, **`infra/`**, **`scripts/`**, and **`requirements.txt`**.

If the zip nested as `CLEVER-main/CLEVER-main/`, go **one level in**.

```powershell
cd <that folder>
dir gateway, infra, scripts, requirements.txt
```

If those four are missing, you are in the wrong directory.

---

## 1. What you need

| Piece | Requirement |
|---|---|
| OS | Windows PowerShell below. Linux/macOS: same steps, `python3` / `source .venv/bin/activate`. |
| Python | 3.11+ (`python --version`) |
| Rancher Desktop | **Running**, container engine = **dockerd (moby)**. **Not Docker Desktop.** |
| RAM | 8 GB+. First start pulls Postgres (pgvector), Redis, and a local MiniLM model. |

Rancher:

```powershell
winget install -e --id SUSE.RancherDesktop
```

Then: Rancher Desktop → Preferences → Container Engine → **dockerd (moby)**. Quit Docker Desktop if it is installed. Wait until the app says **Running**.

This repo’s scripts **refuse** the Docker Desktop context (`desktop-linux`).

---

## 2. Two different keys (do not mix them)

| Key | Where | What it is |
|---|---|---|
| **Gateway key** | Chat page, dashboard field, Swagger **Authorize** | `CLEVER_API_KEY` in `.env`. Local default: `dev-key-change-me` |
| **LLM vendor key** | **Only** `.env` on the server | `LLM_API_KEY` (HTTP API) or AWS keys (Bedrock). Never put this in Swagger or the browser. |

Swagger 401 means you did not click **Authorize** with the **gateway** key. That is expected.

---

## 3. Install (once per machine)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The prompt should show `(.venv)`.

Unit tests (no Docker):

```powershell
python -m pytest -q
```

You want them green. If this fails, stop — the venv is wrong.

---

## 4. Env file

```powershell
copy .env.example .env
```

Open `.env` in VS Code.

### Live HTTP API (chat-completions)

Fill **all four** or leave **all four empty**. A half-filled file will **refuse to start** (it will not silently use mock).

```env
LLM_PROVIDER=auto
LLM_API_KEY=<your vendor API key>
LLM_BASE_URL=https://YOUR_API_BASE_URL
COMPAT_MODEL_CHEAP=<cheap model id>
COMPAT_MODEL_STRONG=<strong model id>
LLM_THINKING=disabled
```

Put matching USD/1M rates in `config/pricing.yaml` or the dollar columns are fiction.

### Or AWS Bedrock

Fill AWS keys (or `AWS_PROFILE`), `AWS_REGION`, `BEDROCK_MODEL_CHEAP`, `BEDROCK_MODEL_STRONG`. Partial Bedrock config also refuses to start.

### Or mock (no spend)

Leave LLM and AWS fields empty. `/health` will say `"provider":"mock"`. The chat UI will tell you it is mock. That is **not** a live model.

Restart uvicorn after every `.env` change.

---

## 5. Start everything

Rancher must already be **Running**.

```powershell
powershell -File scripts\dev.ps1
```

That script:

1. Checks Rancher (dockerd)
2. Creates `.env` from the example if missing
3. Starts Postgres + Redis
4. Applies schema, seeds FAQ, loads synthetic aging
5. Starts the gateway on port **8080** (Ctrl+C stops the gateway, not the containers)

Leave that window open.

### VS Code instead

1. Open **this** folder as the workspace (the one with `gateway/`).
2. Terminal: `powershell -File scripts\first-run.ps1` or task **CLEVER: Rancher stack**.
3. Run / debug: **CLEVER gateway** (uses `.env`).

---

## 6. Open the product

Use **one host** for all tabs: `127.0.0.1` **or** `localhost`, not both.

| URL | What |
|---|---|
| http://127.0.0.1:8080/ | **Chat** — type a prompt, get the answer in the thread |
| http://127.0.0.1:8080/dashboard | **Live metrics** — updates when chat or Swagger calls `/v1/route` |
| http://127.0.0.1:8080/docs | **Swagger** — Authorize first |
| http://127.0.0.1:8080/health | JSON health |

Chat / dashboard gateway-key field: `dev-key-change-me`.

### First prompts in chat

1. `what is today's date` — should be **$0** (RAS template, no LLM).
2. `what is the balance on account 40211` — synthetic aging, **$0** if the fixture loaded.
3. A real sentence (dunning draft, triage) — hits the live model if `.env` is complete; dashboard request count and cost should move.
4. `remit payment for 40211` — **confirm hold**, no model until you click confirm.

### Swagger

1. Open `/docs`.
2. Click **Authorize** → GatewayKey → `dev-key-change-me` → Authorize.
3. `POST /v1/route` → Try it out:

```json
{"query":"what is today's date"}
```

4. Execute. `decision_trace` should include `ras.template` (or classifier / stakes / myelination on other queries).
5. Refresh `/dashboard` — the same call should appear in Recent Requests.

If you skip Authorize, you get **401**. That is not a dead server.

---

## 7. Check that you are live

```powershell
curl.exe -s http://127.0.0.1:8080/health
```

You want `"db":"ok"`, `"redis":"ok"`, and `"provider"` equal to what you configured:

| `provider` | Meaning |
|---|---|
| `openai_compat` | HTTP API from `.env` |
| `bedrock` | Bedrock from `.env` |
| `mock` | No live LLM. Fill `.env` and restart. |

`"live_llm": true` means the default backend is not mock.

---

## 8. Stop

Gateway: Ctrl+C in the `dev.ps1` / uvicorn window.

Containers:

```powershell
docker compose -p clever -f infra\docker-compose.yml down
```

---

## 9. If it does not start

| Symptom | Cause |
|---|---|
| `desktop-linux` / Docker Desktop | Quit Docker Desktop. Rancher = dockerd. `docker context show` |
| Rancher engine not ready | Wait until Rancher is **Running** |
| Incomplete HTTP/Bedrock config | Fill **all** fields or empty **all**. Partial keys refuse startup |
| health `db` / `redis` error | Stack down. Re-run `scripts\first-run.ps1` |
| Chat/dashboard OFFLINE | Gateway not on 8080, or mixed `localhost` vs `127.0.0.1` |
| Swagger 401 | Authorize with `dev-key-change-me` |
| Dashboard MOCK | You are on mock. Not a live API. |
| Port 8080 in use | Stop the other uvicorn. |
| MiniLM slow first request | First embed download. Wait. |

---

## 10. What this is (and is not)

CLEVER sits in front of an LLM: classify → stakes hold on mutations → RAS (template/SQL/FAQ) → cache → compress → cheap/strong routing → log cost vs a strong-tier baseline.

It is **not** production Cvent AR. Analysis and old eval write-ups: `docs/analysis/`.
