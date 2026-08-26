# CLEVER

Laptop AI gateway: chat UI, live cost dashboard, Swagger. Not production (no TLS).

**Full clone-and-run guide:** [`CLEVER_STARTER.md`](CLEVER_STARTER.md)

**Need:** Python 3.11+, Rancher Desktop with **dockerd (moby)** — not Docker Desktop.

## Start

```powershell
cd <folder that contains gateway\ and infra\>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env: paste LLM_API_KEY, LLM_BASE_URL, COMPAT_MODEL_CHEAP, COMPAT_MODEL_STRONG
#   or AWS Bedrock keys + BEDROCK_MODEL_*. Incomplete keys will refuse to start (no silent mock).
powershell -File scripts\dev.ps1
```

Open:

- Chat: http://127.0.0.1:8080/
- Dashboard: http://127.0.0.1:8080/dashboard
- Swagger: http://127.0.0.1:8080/docs → **Authorize** → `dev-key-change-me` (gateway key, not the LLM key)

VS Code: task **CLEVER: Rancher stack**, then launch **CLEVER gateway**.

Without an LLM key, the process may run **mock** and the UI will say so. That is not a live model.

## Honest notes

- Live dashboard polls `/v1/stats`. GET stats is not rate-limited (POST `/v1/route` still is). Opening chat + dashboard used to 429 the shared key.
- Swagger 401 is expected until you click Authorize.
- Analysis write-ups live in `docs/analysis/`.
