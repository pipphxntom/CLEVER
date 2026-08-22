
# Observation — real_test-1

**Observer role:** engineering review of measured behavior, not the pitch.  
**Scope:** mock eval + first DeepSeek eval on Rancher.  
**Companion:** `Real_Test_Result-1.md`

---

## What the system actually is today

A FastAPI gateway in front of DeepSeek that can (1) answer a few lookups without paying, (2) hold mutate intents, (3) project context, (4) cache exact repeats, (5) force the **strong** model on new routes.

It is **not** yet a cheap-model router. It is **not** a quality system for paid answers. It is **not** a source of a 70% savings KPI.

---

## Observations that matter

### 1. The conveyor belt is real
Health, auth, Rancher Postgres/Redis, template/FAQ/SQL, remit hold, exact cache, and a live `deepseek-v4-pro` call with **vendor usage tokens** all happened. That is more than the mock era.

### 2. The first paid-path failure was a $0 lie
FAQ answering a dunning request with an SLA sentence is the worst class of bug: cheap, confident, wrong. Collections cannot ship that. Overlap ≥ 0.5 is a patch, not a knowledge base.

### 3. Cheap models cannot appear under the current learning rule
Cold start forces strong. Updates require `cheap_tried`. Therefore `n_obs` stays 0. Flash is unreachable. This is a **deadlock**, not “not enough data yet.” If we do not fix the update rule, real_test-2 will still show 0% cheap no matter how many authentic queries we send.

### 4. ~11% is the only honest generation saving we have
Same dunning prompt: clever 40 in / $0.000216 vs baseline 72 in / $0.000242, both **pro**. That is compression. Anyone quoting 71% or 93% from this test is misusing the dashboard.

### 5. Grounding is accidental
The model used 40211 and $12,500 (good) and dropped Ada and the invoice id (bad). Quality on strong is `unchecked_strong`. We would cache that letter.

### 6. Classifier is the silent compressor
“Summarize this account” → triage → only account+balance projected. The 95% fat-context cut is partly “we threw away contact on purpose.” That is not the same as intelligent compression.

### 7. Dashboard is a PR risk
A single “Avg Savings” on mixed RAS+LLM+history will be screenshotted. For an AI challenge, that screenshot loses if a judge asks “vs what.”

---

## What winning the challenge requires

Not more neuroscience names. Three mechanical properties:

1. Filters must not answer the wrong class of question.  
2. Cheap must be **explorable** after evidence, then gated by a real lower bound.  
3. Every public number must be labeled by exit (RAS / cache / LLM) and by window.

real_test-1 failed (1) once and structurally fails (2) and (3). Those are the v0.3.1 fixes.

---

*End observation_real_test-1.*
