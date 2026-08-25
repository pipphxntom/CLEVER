# What to paste so CLEVER can talk to both backends

No SSO on this machine. Put values in **`.env`** (gitignored) and restart uvicorn.  
`LLM_PROVIDER=auto` starts every backend whose fields are complete.

Do **not** put secrets in chat if you can avoid it. Filling `.env` locally is enough. If you paste here, treat them as leaked and rotate.

---

## A. OpenAI-compatible API (DeepSeek or any `/v1/chat/completions` host)

| Field | Example | Required |
|---|---|---|
| `LLM_API_KEY` | `sk-…` | yes |
| `LLM_BASE_URL` | `https://api.deepseek.com` | yes |
| `COMPAT_MODEL_CHEAP` | `deepseek-v4-flash` | yes |
| `COMPAT_MODEL_STRONG` | `deepseek-v4-pro` | yes |

Optional: `LLM_THINKING=disabled` (DeepSeek). Leave Bedrock fields empty if you only want this path.

---

## B. AWS Bedrock (Cvent sandbox) — **access keys, not SSO**

Export temporary keys from a machine that *can* SSO (`aws sso login` then `aws configure export-credentials --profile cvt-aws-developer-sandbox --format env`) and paste:

| Field | Example | Required |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | `ASIA…` | yes |
| `AWS_SECRET_ACCESS_KEY` | `…` | yes |
| `AWS_SESSION_TOKEN` | `…` | **yes if the keys are temporary** (SSO/STS). Omit only for a long-lived IAM user. |
| `AWS_REGION` | `us-east-1` unless CAI said otherwise | yes |
| `BEDROCK_MODEL_CHEAP` | inference profile id, e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0` | yes |
| `BEDROCK_MODEL_STRONG` | e.g. `us.anthropic.claude-sonnet-4-6-…` | yes |

Also tell me (not secret):

- Account id of `cvent-sandbox-dev` (so we can check STS `Account` matches)
- Whether region is **not** `us-east-1`
- Exact cheap/strong model IDs CAI enabled, if you already have them

`AWS_PROFILE` is ignored whenever access key + secret are set.

Session tokens expire (often ~1–12 h). When Bedrock calls start failing `ExpiredToken`, export a fresh trio and restart.

---

## C. After you fill `.env`

```powershell
cd D:\CLEVER-main\CLEVER-main
python -m harness.check_bedrock          # STS + list models + optional Converse
python -m uvicorn gateway.main:app --port 8080
curl.exe -s http://127.0.0.1:8080/health
```

Health `backends` should show `"bedrock":"ready"` and/or `"openai_compat":"ready"`.

Pick per request without restarting:

```json
{"query":"what is today's date","llm_backend":"auto"}
{"query":"draft a dunning email","llm_backend":"bedrock"}
{"query":"draft a dunning email","llm_backend":"openai_compat"}
```

Default (`auto`) prefers Bedrock if it is ready, else the OpenAI-compatible API, else mock.

---

## D. Pricing honesty

`config/pricing.yaml` is **one** cheap/strong table. It currently assumes Bedrock Haiku 4.5 / Sonnet 4.6. If you run DeepSeek on `openai_compat` at the same time, dollar columns for that backend are **wrong** until we split the price table. Say so if you will run both in one session.
