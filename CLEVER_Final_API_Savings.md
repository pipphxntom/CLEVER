# CLEVER savings — live API only (mocks excluded)

**Window:** Groups A–H suite, 2026-08-23, gateway `0.4.0`  
**Provider:** DeepSeek via `openai_compat` (`deepseek-v4-flash` / `deepseek-v4-pro`)  
**Log:** `request_log` was **cleared of mock and prior API rows** before this suite. The 55 rows below are this run only.  
**Raw:** `harness/last_suite_ah.json` → `db_window`  
**Dashboard at the time of writing:** same 55 rows (`avg_saved_pct` 59.4 is **not** the number to quote).

Mock results are in `CLEVER_Mock_Results_Separate.md`. They are **not** in any percentage here.

---

## The number to quote (and the ones to refuse)

| Claim | Value | Use it? |
|---|---|---|
| **LLM-only, dollar-weighted** | **43.7%** | **Yes, with the caveats in §2.** `(0.046400 − 0.026140) / 0.046400` on the 33 calls that actually billed tokens. |
| Mixed, dollar-weighted (all 55 rows) | 58.8% | **No** as a product KPI. Includes 22 × $0 exits priced against a strong-tier LLM that would not have been called for “today’s date” or a confirm hold. |
| Dashboard `avg_saved_pct` | 59.4% | **No.** Unweighted mean of per-row percents, RAS/cache/stakes at 100%. The UI itself says this is MIXED. |
| Dashboard `llm_saved_pct` | 32.4% | **Not the $ number.** Mean of per-LLM-row percents. Verbose answers go **negative** and drag the average down vs the dollar mix. |
| Short-circuit rate | **40.0%** | **Yes, as a rate, not a save %.** 22/55 requests cost $0 (4 RAS + 7 cache + 11 stakes pending). |
| “80–95% savings” (old demo) | — | **False.** Not observed. |

**Spend this suite:** **$0.02614** actual vs **$0.06349** strong-tier uncompressed counterfactual.  
**Dollars not spent vs that counterfactual:** **$0.03735**.

That $0.037 is **not** money Cvent would have spent without CLEVER on this exact mix. A large slice is “we did not call a model because we held a remit” and “we answered the date from a regex.” Those are real cost avoidances only if the alternative was “always call pro.”

---

## 1. Exit mix (this is the honest dashboard)

| Exit | n | Cost USD | What it is |
|---|---|---|---|
| RAS (template / structured) | 4 | 0 | Date, days-until, invoice status, plus the date repeat in E4. |
| Cache HIT (exact 2 + semantic 5) | 7 | 0 | Repeats and near-paraphrase triage. |
| Stakes pending (no model) | 11 | 0 | remit / blast / campaign_send / reconciliation / F2×5. |
| **LLM** | **33** | **0.02614** | DeepSeek usage × `pricing.yaml`. |
| **Total logged** | **55** | **0.02614** | |

LLM split:

| Model | Calls | Cost USD |
|---|---|---|
| `deepseek-v4-pro` (strong) | 20 | 0.019113 |
| `deepseek-v4-flash` (cheap) | 13 | 0.007027 |
| **LLM total** | **33** | **0.026140** |
| LLM baseline (strong, uncompressed prompt, same output tokens) | 33 | **0.046400** |
| **LLM dollar-weighted save** | | **43.7%** |

Flash rows in this run typically show **66.6%** saved_pct (cheap vs strong list prices, little compression). That is the **routing** save. Pro rows with empty/tiny context often show **~0% or negative** because the model writes hundreds to thousands of tokens and the baseline undercounts wrapper tokens.

---

## 2. Caveats that change the 43.7%

### 2.1 Eval knob, not production myelination

`.env` has **`N_MIN=6`** (production default **30**). Leftover triage calls in Groups A/C/E pushed `triage:standard` to n_obs≥6 **before** H4, so H4 explored **flash**. Those 13 cheap calls are most of the LLM save.

**Counterfactual if this suite had used production N_MIN=30** (no cheap explore): treat the $0.007027 flash spend as if it had been strong. Flash rows were ~66.6% saved, so strong would have been about 3× that spend ≈ $0.021. LLM actual would be ≈ `$0.02614 − $0.00703 + $0.021 ≈ $0.040`.

| Setting | LLM actual | LLM baseline | LLM save |
|---|---|---|---|
| This run (`N_MIN=6`) | $0.02614 | $0.04640 | **43.7%** |
| Same traffic, `N_MIN=30` (estimate) | ~$0.040 | $0.04640 | **~13–14%** |

**Do not tell a judge that CLEVER saved ~44% in production.** On this mix, with a cold registry and N_MIN=30, you should expect **low-teens LLM save**, plus the 40% short-circuit rate (which is real and mostly stakes/RAS/cache).

### 2.2 Counterfactual is “always strong, uncompressed prompt”

`baseline_method = uncompressed_prompt_strong_tier`. It is **not** “what Cvent pays ChatGPT today.” It is also **not** DeepSeek’s own prompt-cache hit rates. Weekday peak list prices are ~2× the table we used (weekend off-peak, 2026-08-23).

### 2.3 RAS 100% is not a KPI

A date template vs a priced-out `deepseek-v4-pro` call is 100% by construction. The query never needed a model.

### 2.4 Negative rows are real

Empty-context `"triage"`: compressor 2→2 tokens (0%), model wrote 497 tokens, saved_pct **−0.3%**. CLEVER can bill **more** than its own baseline on short prompts. Several H4 pro calls billed **1000–2021** completion tokens on a one-line triage query (`LLM_MAX_TOKENS=1024` — cap is not fully binding or vendor usage includes extra). Verbose models eat the save.

### 2.5 Quality gate delays cache

H5: first miss (pro, −0.2%) was probably not stored → second miss (flash) → third exact HIT $0. Cache save is real **once quality lets a row in**. It is not “every repeat is free.”

### 2.6 Semantic cache 5/20

Near-duplicate H4 queries HIT semantic cache. That **is** a real save ($0 vs another flash/pro call). It also means those five did not train myelination.

---

## 3. What CLEVER actually saved on in this suite

Broken down without pretending they are the same mechanism:

1. **Not calling a model (40% of requests).** Stakes hold + RAS templates/lookups + cache HITs. Dollar-weighted mix 58.8% is almost entirely this, plus (2).
2. **Calling flash instead of pro (~13 of 33 LLM calls, ~66.6% on those rows).** This is the myelination/explore claim. **Only visible because N_MIN=6.**
3. **Compression.** Near-zero on this suite: most queries had empty/tiny context. The 93.8% compressor figure from mock was a **fat noise fixture**, not this suite.
4. **Exact cache** after a stored good answer (D1, H5 third call).

There is **no** 80% number hiding in the LLM legs unless you count $0 exits.

---

## 4. Comparison to earlier live API evals (also not mock)

These are **not** added into the 43.7%. They used the same DeepSeek account before `request_log` was reset.

| Run | File | Honest takeaway |
|---|---|---|
| API gold eval | `CLEVER_API_Test_Results.md` | 13/13 after an FAQ-false-positive fix. LLM spend ~$0.0015. Lookups $0 beat a refusing baseline. |
| Real Test-2 | `observation_real_test-2.md` | Mixed queries; cheap appeared once after leftover n_obs. Generation save was not 80%. |

---

## 5. One-line verdict

**On this live A–H mix, CLEVER’s dollar-weighted save vs “always strong, uncompressed” is 43.7% on paid calls and 58.8% if you include $0 exits. The 43.7% is inflated by an eval `N_MIN=6`. With production `N_MIN=30` the paid-call save on the same traffic is estimated ~14%. The 40% short-circuit rate is the more durable result. Do not use 59.4%, 80%, or 95%.**
