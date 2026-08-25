# Run CLEVER on a fresh clone (Rancher Desktop)

**You need:** Python 3.11+, Rancher Desktop with **dockerd (moby)** (not Docker Desktop).  
**Default:** mock LLM — no API key, no spend.

Code root = the folder that contains `gateway/`, `infra/`, `scripts/`, `requirements.txt`.  
If you unzipped and see `CLEVER-main/CLEVER-main/`, `cd` into the inner one.

---

## Copy-paste (PowerShell)

```powershell
# 0) go to the code root
cd <path-to-folder-with-gateway-and-infra>

# 1) Python venv
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# 2) unit tests (no Docker)
python -m pytest -q

# 3) local Postgres + Redis via Rancher (creates .env from .env.example if missing)
powershell -File scripts\first-run.ps1

# 4) gateway (keep this window open)
python -m uvicorn gateway.main:app --port 8080
```

In a **second** PowerShell window (venv on):

```powershell
curl.exe -s http://127.0.0.1:8080/health
curl.exe -s -X POST http://127.0.0.1:8080/v1/route -H "Content-Type: application/json" -H "X-API-Key: dev-key-change-me" -d "{\"query\":\"what is today's date\"}"
```

Open the dashboard: [http://127.0.0.1:8080/](http://127.0.0.1:8080/)  
Leave the API key field as `dev-key-change-me`.

`/health` should be `"provider":"mock"` (or `auto` with only `mock` ready), `"db":"ok"`, `"redis":"ok"`.  
The date query should cost `$0` (template short-circuit).

---

## Rancher checklist

1. Install: `winget install -e --id SUSE.RancherDesktop`
2. Open Rancher Desktop → Preferences → Container Engine → **dockerd (moby)**
3. Quit Docker Desktop if it is installed
4. Wait until Rancher shows **Running**
5. `scripts\first-run.ps1` refuses the Docker Desktop context (`desktop-linux`)

---

## Optional: live HTTP API (spends money)

Edit `.env` (never commit it):

```env
LLM_PROVIDER=openai_compat
LLM_API_KEY=<your API key>
LLM_BASE_URL=https://YOUR_API_BASE_URL
COMPAT_MODEL_CHEAP=<cheap model id>
COMPAT_MODEL_STRONG=<strong model id>
LLM_THINKING=disabled
```

Match `config/pricing.yaml` to those models. Restart uvicorn. `/health` must show `"provider":"openai_compat"`.

Live evals were run with **an AI API key** on this HTTP adapter. Do not mix those numbers with mock or Bedrock runs.

---

## Optional: AWS Bedrock

See `WHAT_TO_PROVIDE.md`. Static access keys (no SSO required on the clone host).

---

## Stop

Gateway: Ctrl+C in the uvicorn window.  
Stack: `docker compose -p clever -f infra\docker-compose.yml down`

---

More detail: `CLEVER_STARTER.md`. Security: `SECURITY.md`. This is a laptop build — no TLS, no SSO.
