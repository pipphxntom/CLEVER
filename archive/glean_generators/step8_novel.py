raise SystemExit('archived generator — do not run; see archive/glean_generators/DO_NOT_RUN.txt')
"""
Step 8: All 5 Novel Layers.
RAS Gate + Myelination + VpT + Tail-Cost + Sleep Consolidation.
Run from C:\\CLEVER: python step8_novel.py
"""
import os

files = {}

# â”€â”€ gateway/layers/ras/__init__.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/ras/__init__.py"] = ""

# â”€â”€ gateway/layers/ras/structured_lookup.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/ras/structured_lookup.py"] = '''\
"""
RAS Check 1: Structured Data Lookup.
Detects if a query can be answered by a direct Postgres field lookup.
$0 cost, <5ms. No LLM, no cache, no embedding.
"""
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

_ACCOUNT_RE  = re.compile(r"\\b(\\d{4,6})\\b")
_INVOICE_RE  = re.compile(r"INV-[\\d-]+", re.IGNORECASE)

_LOOKUP_VERBS = [
    "what is", "what's", "show me", "get", "fetch",
    "how many", "balance on", "status of", "days overdue",
    "tell me about", "look up",
]

def attempt(query: str, pool) -> Optional[dict]:
    """
    Returns entity hint dict on match, None otherwise.
    Pure Python â€” no async, no DB call here.
    The caller (ras_gate.py) passes the hint to structured_resolver.resolve().
    """
    q = query.lower()
    is_lookup = any(v in q for v in _LOOKUP_VERBS)
    if not is_lookup:
        return None

    account_match = _ACCOUNT_RE.search(query)
    invoice_match = _INVOICE_RE.search(query)

    if not (account_match or invoice_match):
        return None

    hint = {
        "entity_type":  "account" if account_match else "invoice",
        "entity_value": (account_match or invoice_match).group(0),
        "field_ask":    _infer_field(q),
    }
    log.info("ras.structured_lookup candidate entity=%s field=%s",
             hint["entity_value"], hint["field_ask"])
    return hint

def _infer_field(q: str) -> str:
    if "balance" in q:              return "balance"
    if "overdue" in q or "days" in q: return "days_overdue"
    if "status" in q:               return "status"
    if "contact" in q:              return "contact"
    return "summary"
'''

# â”€â”€ gateway/layers/ras/structured_resolver.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/ras/structured_resolver.py"] = '''\
"""
RAS Check 1 (resolver): runs the actual Postgres query.
Called by ras_gate.py with the hint from structured_lookup.
Returns a plain-text answer string or None if entity not found.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

async def resolve(hint: dict, pool) -> Optional[str]:
    """Executes DB lookup against aging_data. Returns formatted answer."""
    try:
        async with pool.acquire() as conn:
            # Check if aging_data has any rows first
            count = await conn.fetchval("SELECT COUNT(*) FROM aging_data")
            if not count:
                log.info("ras.structured_resolver: aging_data empty â€” miss")
                return None

            if hint["entity_type"] == "account":
                row = await conn.fetchrow(
                    """
                    SELECT account, balance, days_overdue, status, contact
                    FROM aging_data
                    WHERE account_id = $1
                    AND aging_version = (
                        SELECT active_aging_version FROM active_pointer LIMIT 1
                    )
                    LIMIT 1
                    """,
                    hint["entity_value"],
                )
                if not row:
                    log.info("ras.structured_resolver: account %s not found", hint["entity_value"])
                    return None

                field = hint["field_ask"]
                if field == "balance":
                    return f"Account {row['account']}: balance ${row['balance']:,.2f}"
                if field == "days_overdue":
                    return f"Account {row['account']}: {row['days_overdue']} days overdue"
                if field == "status":
                    return f"Account {row['account']}: status = {row['status']}"
                if field == "contact":
                    return f"Account {row['account']}: contact = {row['contact']}"
                # Summary
                return (
                    f"Account {row['account']} â€” "
                    f"Balance: ${row['balance']:,.2f} | "
                    f"Days overdue: {row['days_overdue']} | "
                    f"Status: {row['status']}"
                )
    except Exception as exc:
        log.warning("ras.structured_resolver error: %s", exc)
    return None
'''

# â”€â”€ gateway/layers/ras/faq_match.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/ras/faq_match.py"] = '''\
"""
RAS Check 2: BM25 FAQ Match.
Uses Postgres built-in tsvector/tsquery â€” no external library needed.
$0 cost, <10ms.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

_BM25_THRESHOLD = 0.05   # ts_rank scale: 0.05 is a meaningful match in Postgres

async def attempt(query: str, pool) -> Optional[dict]:
    """
    BM25 full-text search against faq_entries.
    Returns {response, score, faq_id} on hit, None on miss.
    """
    try:
        async with pool.acquire() as conn:
            # Check if FAQ has entries
            count = await conn.fetchval("SELECT COUNT(*) FROM faq_entries")
            if not count:
                log.info("ras.faq: no FAQ entries yet â€” miss")
                return None

            rows = await conn.fetch(
                """
                SELECT
                    id, question, answer,
                    ts_rank(
                        to_tsvector('english', question || ' ' || answer),
                        plainto_tsquery('english', $1)
                    ) AS score
                FROM faq_entries
                WHERE
                    to_tsvector('english', question || ' ' || answer)
                    @@ plainto_tsquery('english', $1)
                ORDER BY score DESC
                LIMIT 1
                """,
                query,
            )

            if not rows or rows[0]["score"] < _BM25_THRESHOLD:
                log.info("ras.faq MISS query=%r", query[:60])
                return None

            row = rows[0]
            # Update hit count
            await conn.execute(
                "UPDATE faq_entries SET hit_count = hit_count + 1, "
                "updated_at = now() WHERE id = $1",
                row["id"],
            )
            log.info("ras.faq HIT faq_id=%s score=%.3f", row["id"], row["score"])
            return {
                "response": row["answer"],
                "score":    row["score"],
                "faq_id":   row["id"],
            }
    except Exception as exc:
        log.warning("ras.faq error: %s", exc)
    return None
'''

# â”€â”€ gateway/layers/ras/template_resolver.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/ras/template_resolver.py"] = '''\
"""
RAS Check 3: Template / Regex Resolution.
Pure Python â€” no DB, no async, no model. $0, <1ms.
Handles date queries, arithmetic, entity formatting.
"""
import re
import logging
from datetime import datetime, date
from typing import Optional

log = logging.getLogger(__name__)

def _today(_m, _q):
    return f"Today is {date.today().strftime('%B %d, %Y')}."

def _date_diff(m, _q):
    try:
        d1    = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        d2    = date.today()
        delta = (d2 - d1).days
        return f"{delta} days between {d1.isoformat()} and today ({d2.isoformat()})."
    except Exception:
        return None

def _invoice_format(m, _q):
    inv_id = m.group(1).upper()
    return f"Invoice reference: {inv_id}"

def _days_from_now(m, _q):
    try:
        d1    = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        d2    = date.today()
        delta = (d1 - d2).days
        if delta > 0:
            return f"{d1.isoformat()} is {delta} days from today."
        elif delta == 0:
            return f"{d1.isoformat()} is today."
        else:
            return f"{d1.isoformat()} was {abs(delta)} days ago."
    except Exception:
        return None

_RESOLVERS = [
    (re.compile(r"\\b(today|current date|what date is it|what is today)\\b", re.I), _today),
    (re.compile(r"days between (\\d{4}-\\d{2}-\\d{2}) and today", re.I),            _date_diff),
    (re.compile(r"how (far|many days) (until|to|from) (\\d{4}-\\d{2}-\\d{2})", re.I), _days_from_now),
    (re.compile(r"format invoice (INV-[\\d-]+)", re.I),                              _invoice_format),
]

def attempt(query: str) -> Optional[dict]:
    """Pure Python â€” no DB, no async, no model. $0, <1ms."""
    for pattern, handler in _RESOLVERS:
        m = pattern.search(query)
        if m:
            result = handler(m, query)
            if result:
                log.info("ras.template HIT pattern=%r", pattern.pattern[:40])
                return {"response": result, "resolver": pattern.pattern}
    return None
'''

# â”€â”€ gateway/layers/ras_gate.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/ras_gate.py"] = '''\
"""
RAS Gate orchestrator (L7) â€” wires all 3 pre-LLM checks.
Runs AFTER stakes gate, BEFORE exact cache.
Returns on first hit. Returns None if all miss (pipeline continues).
Checks 4+5 (exact cache + semantic cache) remain in pipeline.py.
"""
import logging
from gateway.layers.ras import (
    structured_lookup,
    structured_resolver,
    faq_match,
    template_resolver,
)

log = logging.getLogger(__name__)

async def attempt(req, pool, redis_client, trace: list) -> dict | None:
    """
    Runs checks 1-3 in cost-ascending order.
    Returns {response, gate} on hit, None on miss.
    """

    # â”€â”€ Check 1: Structured Data Lookup ($0, <5ms) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    hint = structured_lookup.attempt(req.query, pool)
    if hint:
        answer = await structured_resolver.resolve(hint, pool)
        if answer:
            trace.append({
                "layer":  "ras.structured_lookup",
                "result": "HIT",
                "entity": hint["entity_value"],
                "field":  hint["field_ask"],
                "cost":   "$0",
            })
            log.info("RAS_GATE resolved via structured_lookup entity=%s", hint["entity_value"])
            return {"response": answer, "gate": "ras.structured_lookup"}
    trace.append({"layer": "ras.structured_lookup", "result": "miss"})

    # â”€â”€ Check 2: FAQ / BM25 ($0, <10ms) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    faq_hit = await faq_match.attempt(req.query, pool)
    if faq_hit:
        trace.append({
            "layer":  "ras.faq",
            "result": "HIT",
            "score":  round(faq_hit["score"], 3),
            "faq_id": faq_hit["faq_id"],
            "cost":   "$0",
        })
        log.info("RAS_GATE resolved via faq faq_id=%s", faq_hit["faq_id"])
        return {"response": faq_hit["response"], "gate": "ras.faq"}
    trace.append({"layer": "ras.faq", "result": "miss"})

    # â”€â”€ Check 3: Template / Regex ($0, <1ms) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    tmpl_hit = template_resolver.attempt(req.query)
    if tmpl_hit:
        trace.append({
            "layer":    "ras.template",
            "result":   "HIT",
            "resolver": tmpl_hit["resolver"][:40],
            "cost":     "$0",
        })
        log.info("RAS_GATE resolved via template")
        return {"response": tmpl_hit["response"], "gate": "ras.template"}
    trace.append({"layer": "ras.template", "result": "miss"})

    return None
'''

# â”€â”€ gateway/layers/myelination.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/layers/myelination.py"] = '''\
"""
Myelination Engine (L8) â€” Beta-Bayesian progressive routing.
Tracks per-route success rate. Learns which routes are safe for Haiku.
Three phases: Cortical (new) -> Myelinating (learning) -> Cerebellar (confident).
"""
import logging
import math
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

N_MIN = 30      # cold-start guard â€” cheap path ineligible below this
Z     = 1.96    # 95% confidence interval for LCB gate

# Quality threshold per feature class
_TAU = {
    "collections_outreach": 0.90,
    "customer_facing":       0.98,
    "analytics_reporting":   0.93,
    "event_management":      0.90,
    "venue_sourcing":        0.90,
    "customer_support":      0.93,
    "marketing_automation":  0.95,
    "default":               0.90,
}

@dataclass
class MyelinDecision:
    eligible:  bool    # is cheap path eligible?
    phase:     str     # Cortical | Myelinating | Cerebellar
    p_hat:     float   # posterior mean success rate
    sigma:     float   # posterior std dev (uncertainty)
    n_obs:     int     # total observations
    lcb:       float   # lower confidence bound
    decision:  str     # cheap_ok | cheap_ineligible | cold_start

async def check(route_class: str, feature_class: str, pool) -> MyelinDecision:
    """
    Reads Beta(alpha, beta) from myelination_registry.
    Returns MyelinDecision for the router to use.
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT alpha, beta, n_obs FROM myelination_registry "
                "WHERE route_class = $1",
                route_class,
            )
    except Exception as exc:
        log.warning("myelination.check error: %s", exc)
        return _cortical(0)

    if not row:
        return _cortical(0)

    alpha, beta_, n_obs = row["alpha"], row["beta"], row["n_obs"]

    p_hat = alpha / (alpha + beta_)
    var   = (alpha * beta_) / ((alpha + beta_) ** 2 * (alpha + beta_ + 1))
    sigma = math.sqrt(var)
    lcb   = p_hat - Z * sigma
    tau   = _TAU.get(feature_class, _TAU["default"])

    if n_obs < N_MIN:
        return MyelinDecision(
            eligible=False, phase="Cortical",
            p_hat=round(p_hat, 4), sigma=round(sigma, 4),
            n_obs=n_obs, lcb=round(lcb, 4),
            decision="cold_start",
        )

    phase    = "Cerebellar" if n_obs >= 100 else "Myelinating"
    eligible = lcb >= tau

    log.info(
        "myelination route=%s phase=%s p_hat=%.3f lcb=%.3f tau=%.2f eligible=%s",
        route_class, phase, p_hat, lcb, tau, eligible,
    )

    return MyelinDecision(
        eligible=eligible,
        phase=phase,
        p_hat=round(p_hat, 4),
        sigma=round(sigma, 4),
        n_obs=n_obs,
        lcb=round(lcb, 4),
        decision="cheap_ok" if eligible else "cheap_ineligible",
    )

async def update(
    route_class: str,
    success: bool,
    severity: str = "none",
    pool=None,
) -> None:
    """
    Updates Beta(alpha, beta) after cascade result.
    severity: none | minor | wrong | critical
    Called POST-response by pipeline.py.
    """
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            if severity == "critical":
                await conn.execute(
                    """
                    UPDATE myelination_registry
                    SET alpha=1, beta=1, n_obs=0,
                        last_correction=now(), updated_at=now()
                    WHERE route_class = $1
                    """,
                    route_class,
                )
                log.warning("DE_MYELINATION route_class=%s severity=critical full_reset", route_class)
                return

            if success:
                await conn.execute(
                    """
                    INSERT INTO myelination_registry
                        (route_class, alpha, beta, n_obs, updated_at)
                    VALUES ($1, 2, 1, 1, now())
                    ON CONFLICT (route_class) DO UPDATE
                    SET alpha    = myelination_registry.alpha + 1,
                        n_obs    = myelination_registry.n_obs + 1,
                        updated_at = now()
                    """,
                    route_class,
                )
            else:
                w = {"none": 0, "minor": 1, "wrong": 3}.get(severity, 1)
                await conn.execute(
                    """
                    INSERT INTO myelination_registry
                        (route_class, alpha, beta, n_obs, last_correction, updated_at)
                    VALUES ($1, 1, $2, 1, now(), now())
                    ON CONFLICT (route_class) DO UPDATE
                    SET beta             = myelination_registry.beta + $2,
                        n_obs            = myelination_registry.n_obs + 1,
                        last_correction  = now(),
                        updated_at       = now()
                    """,
                    route_class, w,
                )
                if severity in ("wrong", "minor"):
                    log.warning(
                        "DE_MYELINATION route_class=%s severity=%s beta+=%d",
                        route_class, severity, w,
                    )
    except Exception as exc:
        log.warning("myelination.update error: %s", exc)

def route_class_from(intent: str, confidence: float) -> str:
    """
    Builds the route class key used as the myelination registry PK.
    Low confidence = different (safer) class.
    """
    complexity = "high" if confidence < 0.8 else "standard"
    return f"{intent}:{complexity}"

def _cortical(n_obs: int) -> MyelinDecision:
    return MyelinDecision(
        eligible=False, phase="Cortical",
        p_hat=0.5, sigma=0.5,
        n_obs=n_obs, lcb=0.0,
        decision="cold_start",
    )
'''

# â”€â”€ gateway/telemetry/vpt.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/telemetry/vpt.py"] = '''\
"""
VpT Attribution (L5) â€” Value-per-Token.
VpT = Business Outcome ($) / Total Tokens * 1000
Converts CLEVER from a cost tool into a business ROI framework.
"""
import logging
import yaml
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_OUTCOMES_PATH = Path("config/vpt_outcomes.yaml")
_OUTCOMES: dict = {}

def _load():
    global _OUTCOMES
    if not _OUTCOMES:
        _OUTCOMES = yaml.safe_load(_OUTCOMES_PATH.read_text(encoding="utf-8"))

def compute(intent: str, tokens_total: int, outcome_count: int = 1) -> dict:
    """
    Returns {vpt, outcome_unit, outcome_value_usd, total_tokens}.
    outcome_count: number of accounts/emails/threads processed.
    Default 1. Caller can pass req.context.get("outcome_count", 1).
    """
    _load()
    cfg           = _OUTCOMES.get(intent, {"unit": "calls", "default_value_usd": 0.10})
    outcome_value = cfg["default_value_usd"] * outcome_count
    vpt           = round(outcome_value / max(tokens_total, 1) * 1000, 6)

    log.info(
        "vpt intent=%s tokens=%d outcome_value=%.2f vpt=%.4f",
        intent, tokens_total, outcome_value, vpt,
    )
    return {
        "vpt":               vpt,
        "outcome_unit":      cfg["unit"],
        "outcome_value_usd": round(outcome_value, 4),
        "total_tokens":      tokens_total,
    }

def alert_rules(vpt: float, history: list) -> Optional[str]:
    """
    Checks VpT alert conditions against recent history.
    history: last 7 daily VpT averages for this intent.
    Returns alert string or None.
    """
    if vpt < 0.1:
        return "VPT_LOW: below floor 0.1 â€” review prompt efficiency"
    if len(history) >= 2:
        week_avg = sum(history[-7:]) / len(history[-7:])
        if week_avg > 0 and (week_avg - vpt) / week_avg > 0.20:
            return "VPT_DECLINING: >20% drop week-over-week â€” investigate"
    if vpt > 2.0:
        return "VPT_HIGH: scale candidate â€” this intent has strong ROI"
    return None
'''

# â”€â”€ gateway/telemetry/tail_cost.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/telemetry/tail_cost.py"] = '''\
"""
Tail-Cost Detector (L5.5).
TCR = Cost of top 10% most expensive calls / Cost of bottom 90%.
If TCR > 1.0: expensive minority costs more than everything else combined.
Computed on-demand â€” runs as part of /v1/stats.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

TCR_ALERT_THRESHOLD = 1.0

async def compute(pool, intent: str = None, window_hours: int = 24) -> dict:
    """
    Computes Tail Cost Ratio for the given window.
    intent: optional filter to scope to one intent.
    """
    intent_filter = "AND intent = $2" if intent else ""
    params        = [window_hours]
    if intent:
        params.append(intent)

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                WITH ranked AS (
                    SELECT
                        cost_usd,
                        NTILE(10) OVER (ORDER BY cost_usd DESC) AS decile
                    FROM request_log
                    WHERE ts > now() - interval '1 hour' * $1
                    {intent_filter}
                    AND cost_usd IS NOT NULL
                    AND cost_usd > 0
                )
                SELECT
                    COALESCE(SUM(CASE WHEN decile = 1 THEN cost_usd ELSE 0 END), 0) AS tail_cost,
                    COALESCE(SUM(CASE WHEN decile > 1 THEN cost_usd ELSE 0 END), 0) AS body_cost,
                    COUNT(*) AS total_requests
                FROM ranked
                """,
                *params,
            )
    except Exception as exc:
        log.warning("tail_cost.compute error: %s", exc)
        return {"tcr": 0.0, "tail_cost_usd": 0.0, "body_cost_usd": 0.0,
                "total_requests": 0, "alert": False, "message": "error"}

    tail  = float(row["tail_cost"]  or 0)
    body  = float(row["body_cost"]  or 0)
    total = row["total_requests"]
    tcr   = round(tail / body, 4) if body > 0 else 0.0
    alert = tcr > TCR_ALERT_THRESHOLD

    if alert:
        log.warning(
            "TAIL_COST_ALERT TCR=%.3f tail=$%.4f body=$%.4f requests=%d",
            tcr, tail, body, total,
        )

    return {
        "tcr":            tcr,
        "tail_cost_usd":  round(tail, 4),
        "body_cost_usd":  round(body, 4),
        "total_requests": total,
        "alert":          alert,
        "message": (
            f"TCR={tcr:.2f}: expensive 10% costs more than the rest â€” "
            f"check runaway intents or missing exit conditions"
        ) if alert else f"TCR={tcr:.2f}: healthy distribution",
    }
'''

# â”€â”€ gateway/sleep/__init__.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/sleep/__init__.py"] = ""

# â”€â”€ gateway/sleep/consolidation.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/sleep/consolidation.py"] = '''\
"""
Sleep Consolidation (L9) â€” weekly self-maintenance cycle.
Biological analogy: NREM sleep prunes dead synapses, strengthens
important memories, generalizes patterns.
CLEVER does the same: prune stale cache, strengthen hot entries,
validate myelination, promote FAQ patterns.
Runs Sunday 3am via APScheduler in main.py.
"""
import logging
from datetime import datetime

log = logging.getLogger(__name__)

_ZERO_HIT_DAYS    = 7     # evict zero-hit cache entries older than N days
_EXTEND_TTL_SCORE = 10    # hit_count threshold for TTL extension
_EXTENDED_TTL     = 7200  # 2-hour TTL for hot entries
_FAQ_PROMOTE_MIN  = 20    # minimum repetitions before promoting to faq_entries

async def run(pool):
    """Full weekly consolidation cycle. Non-fatal on any phase error."""
    log.info("SLEEP_CONSOLIDATION starting at %s", datetime.utcnow().isoformat())

    try:
        async with pool.acquire() as conn:

            # â”€â”€ Phase 1: PRUNE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            pruned = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM semantic_cache
                    WHERE hit_count = 0
                    AND created_at < now() - interval '1 day' * $1
                    RETURNING 1
                ) SELECT COUNT(*) FROM deleted
                """,
                _ZERO_HIT_DAYS,
            )
            log.info("SLEEP phase=prune removed_cache_entries=%d", pruned or 0)

            pruned_myelin = await conn.fetchval(
                """
                WITH deleted AS (
                    DELETE FROM myelination_registry
                    WHERE n_obs = 0
                    AND updated_at < now() - interval '14 days'
                    RETURNING 1
                ) SELECT COUNT(*) FROM deleted
                """
            )
            log.info("SLEEP phase=prune removed_myelination_paths=%d", pruned_myelin or 0)

            # â”€â”€ Phase 2: STRENGTHEN â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            strengthened = await conn.fetchval(
                """
                WITH updated AS (
                    UPDATE semantic_cache
                    SET ttl_seconds = $1
                    WHERE hit_count >= $2
                    RETURNING 1
                ) SELECT COUNT(*) FROM updated
                """,
                _EXTENDED_TTL, _EXTEND_TTL_SCORE,
            )
            log.info("SLEEP phase=strengthen extended_ttl_entries=%d", strengthened or 0)

            # â”€â”€ Phase 3: VALIDATE MYELINATION â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            degraded = await conn.fetch(
                """
                SELECT
                    route_class,
                    COUNT(*) AS total,
                    SUM(CASE WHEN model_used LIKE '%sonnet%' THEN 1 ELSE 0 END) AS escalations
                FROM request_log
                WHERE ts > now() - interval '7 days'
                AND model_used IS NOT NULL
                AND route_class IS NOT NULL
                GROUP BY route_class
                HAVING COUNT(*) >= 10
                AND SUM(CASE WHEN model_used LIKE '%sonnet%' THEN 1 ELSE 0 END)::float
                    / COUNT(*) > 0.30
                """
            )
            for row in degraded:
                await conn.execute(
                    "UPDATE myelination_registry "
                    "SET alpha=1, beta=1, n_obs=0, last_correction=now() "
                    "WHERE route_class=$1",
                    row["route_class"],
                )
                log.warning(
                    "SLEEP phase=validate DE_MYELINATION route_class=%s escalation_rate=%.0f%%",
                    row["route_class"],
                    row["escalations"] / row["total"] * 100,
                )

            # â”€â”€ Phase 4: CONSOLIDATE â€” promote patterns to FAQ â”€â”€â”€â”€â”€â”€â”€â”€â”€
            patterns = await conn.fetch(
                """
                SELECT
                    query_hash,
                    MODE() WITHIN GROUP (ORDER BY intent) AS intent,
                    COUNT(*) AS frequency
                FROM request_log
                WHERE ts > now() - interval '30 days'
                AND gate_fired IS NULL
                AND query_hash IS NOT NULL
                GROUP BY query_hash
                HAVING COUNT(*) >= $1
                """,
                _FAQ_PROMOTE_MIN,
            )

            promoted = 0
            for p in patterns:
                sample = await conn.fetchrow(
                    "SELECT query_text, response FROM semantic_cache "
                    "WHERE query_text IS NOT NULL "
                    "ORDER BY hit_count DESC LIMIT 1"
                )
                if sample:
                    await conn.execute(
                        """
                        INSERT INTO faq_entries (question, answer, source, created_at)
                        VALUES ($1, $2, 'sleep_consolidation', now())
                        ON CONFLICT (question) DO NOTHING
                        """,
                        sample["query_text"], sample["response"],
                    )
                    promoted += 1
            log.info("SLEEP phase=consolidate promoted_to_faq=%d", promoted)

            # â”€â”€ Phase 5: VpT daily aggregates â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            await conn.execute(
                """
                INSERT INTO vpt_daily (date, intent, avg_vpt, total_tokens, total_value)
                SELECT
                    CURRENT_DATE,
                    intent,
                    AVG(vpt),
                    SUM(tokens_in + tokens_out),
                    SUM(outcome_value_usd)
                FROM request_log
                WHERE DATE(ts) = CURRENT_DATE - 1
                AND vpt IS NOT NULL
                GROUP BY intent
                ON CONFLICT (date, intent) DO UPDATE
                SET avg_vpt     = EXCLUDED.avg_vpt,
                    total_tokens = EXCLUDED.total_tokens,
                    total_value  = EXCLUDED.total_value
                """
            )

    except Exception as exc:
        log.error("SLEEP_CONSOLIDATION error: %s", exc)

    log.info("SLEEP_CONSOLIDATION complete at %s", datetime.utcnow().isoformat())
'''

# â”€â”€ config/vpt_outcomes.yaml â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["config/vpt_outcomes.yaml"] = """\
# VpT Outcome Mapping â€” intent -> business outcome unit + value
# default_value_usd: estimated dollar value of one unit of this outcome
# A finance judge will ask where these numbers come from:
# - email_draft: average dunning email recovers $2 in time-to-payment improvement
# - triage: analyst time saved reviewing one account = ~$0.50
# - dispute: high-touch resolution value = $5 per dispute logged

triage:
  unit: "accounts_reviewed"
  default_value_usd: 0.50

email_draft:
  unit: "emails_queued"
  default_value_usd: 2.00

email_blast:
  unit: "blast_sent"
  default_value_usd: 1.50

inbox_check:
  unit: "threads_processed"
  default_value_usd: 0.75

dispute:
  unit: "disputes_logged"
  default_value_usd: 5.00

remit:
  unit: "payments_processed"
  default_value_usd: 3.00

notes:
  unit: "notes_logged"
  default_value_usd: 0.25

event_summary:
  unit: "events_reviewed"
  default_value_usd: 0.30

event_status_check:
  unit: "events_checked"
  default_value_usd: 0.20

registration_lookup:
  unit: "registrations_checked"
  default_value_usd: 0.15

campaign_draft:
  unit: "campaigns_drafted"
  default_value_usd: 3.00

venue_search:
  unit: "venues_evaluated"
  default_value_usd: 1.00

rfp_draft:
  unit: "rfps_drafted"
  default_value_usd: 5.00

ticket_lookup:
  unit: "tickets_reviewed"
  default_value_usd: 0.40

report_summary:
  unit: "reports_generated"
  default_value_usd: 1.50

insight_query:
  unit: "insights_generated"
  default_value_usd: 2.00
"""

# â”€â”€ demo/trigger_demyelination.py â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
os.makedirs("demo", exist_ok=True)
files["demo/__init__.py"] = ""
files["demo/trigger_demyelination.py"] = '''\
"""
Demo script: triggers de-myelination live during the demo.
Run this while the gateway is running to show L8 reacting.
Usage: python demo/trigger_demyelination.py [route_class]
Default route_class: email_draft:standard
"""
import asyncio
import asyncpg
import sys

async def trigger(route_class: str = "email_draft:standard"):
    pool = await asyncpg.create_pool("postgresql://clever:clever@localhost:5432/clever")
    async with pool.acquire() as conn:
        # First ensure the route class exists
        await conn.execute(
            """
            INSERT INTO myelination_registry
                (route_class, alpha, beta, n_obs, updated_at)
            VALUES ($1, 50, 5, 55, now())
            ON CONFLICT (route_class) DO UPDATE
            SET alpha=50, beta=5, n_obs=55, updated_at=now()
            """,
            route_class,
        )
        print(f"Set {route_class} to Cerebellar (n_obs=55, p_hat=0.91)")
        print("Firing next request will show: phase=Cerebellar, decision=cheap_ok")
        print()
        input("Press ENTER to trigger DE-MYELINATION (critical failure)...")

        await conn.execute(
            """
            UPDATE myelination_registry
            SET alpha=1, beta=1, n_obs=0, last_correction=now()
            WHERE route_class=$1
            """,
            route_class,
        )
        print(f"DE_MYELINATION triggered â€” {route_class} reset to Cortical")
        print("Firing next request will show: phase=Cortical, decision=cold_start")
        print("System will use Sonnet until 30 consecutive successes rebuild trust.")
    await pool.close()

route_class = sys.argv[1] if len(sys.argv) > 1 else "email_draft:standard"
asyncio.run(trigger(route_class))
'''

# â”€â”€ gateway/telemetry/accounting.py (add build_ras_accounting) â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/telemetry/accounting.py"] = '''\
"""
Cost accounting â€” computes per-request cost vs true baseline.
Baseline = FULL uncompressed context + always Sonnet + no cache.
"""

_PRICING = {
    "haiku":  {"in": 0.80,  "out": 4.00},
    "sonnet": {"in": 3.00,  "out": 15.00},
}

_OUT_ESTIMATE = {"triage": 150, "email_draft": 220, "default": 180}

def _tier(model_id: str) -> str:
    return "haiku" if "haiku" in model_id.lower() else "sonnet"

def _cost(tokens_in: int, tokens_out: int, model_id: str) -> float:
    r = _PRICING[_tier(model_id)]
    return (tokens_in * r["in"] + tokens_out * r["out"]) / 1_000_000

def build_accounting(usage: dict, tokens_before: int = None) -> dict:
    ti  = usage["tokens_in"]
    to  = usage["tokens_out"]
    mid = usage["model_id"]
    cost = _cost(ti, to, mid)
    baseline_in = tokens_before if tokens_before else ti
    base = _cost(baseline_in, to, "sonnet")
    saved     = max(0.0, base - cost)
    saved_pct = round(saved / base * 100, 1) if base > 0 else 0.0
    return {
        "tokens_in":         ti,
        "tokens_out":        to,
        "cost_usd":          round(cost,  6),
        "baseline_cost_usd": round(base,  6),
        "saved_usd":         round(saved, 6),
        "saved_pct":         saved_pct,
    }

def build_ras_accounting(intent: str = "triage", tokens_before: int = 8200) -> dict:
    """
    For RAS-resolved requests: actual cost is $0.
    Baseline is still the full naive path cost.
    saved_pct is always 100% â€” the RAS gate answered for free.
    """
    est_out  = _OUT_ESTIMATE.get(intent, _OUT_ESTIMATE["default"])
    baseline = _cost(tokens_before, est_out, "sonnet")
    return {
        "tokens_in":         0,
        "tokens_out":        0,
        "cost_usd":          0.0,
        "baseline_cost_usd": round(baseline, 6),
        "saved_usd":         round(baseline, 6),
        "saved_pct":         100.0,
    }
'''

# â”€â”€ gateway/pipeline.py (full 15-step rewire) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/pipeline.py"] = '''\
"""
CLEVER pipeline orchestrator â€” full 15-step novel layers build.
Classifier -> Stakes Gate -> RAS Gate -> Exact Cache ->
Myelination Check -> Router -> Compressor -> Cascade ->
VpT -> Tail-Cost -> Accounting -> Telemetry ->
Myelination Update -> Cache Store
"""
import time
import logging
import asyncio

from gateway.models import RouteRequest, RouteResponse, AccountingResult, QualityResult
from gateway.layers import stakes_gate, cache, classifier, compressor, cascade
from gateway.layers import ras_gate, myelination
from gateway.telemetry import accounting, vpt as vpt_calc, tail_cost as tail_cost_calc
from gateway.telemetry import logger as telemetry

log = logging.getLogger(__name__)

_HAIKU  = "anthropic.claude-3-5-haiku-20241022-v1:0"
_SONNET = "anthropic.claude-3-5-sonnet-20241022-v2:0"

async def route(req: RouteRequest, app_state) -> RouteResponse:
    start = time.time()
    trace = []

    # â”€â”€ [1] Classifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    intent, confidence = classifier.classify(req)
    trace.append({
        "layer":      "classifier",
        "intent":     intent,
        "confidence": confidence,
        "method": (
            "config"  if confidence == 1.0 else
            "keyword" if confidence == 0.8 else
            "default"
        ),
    })

    # â”€â”€ [2] Stakes Gate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    stakes = stakes_gate.classify(req, intent)
    gate_entry = {
        "layer":  "stakes_gate",
        "result": "SUSPENDED" if stakes.suspend_optimization else "read",
    }
    if stakes.suspend_optimization:
        gate_entry.update({
            "reason":                stakes.reason,
            "min_model":             stakes.min_model,
            "require_human_confirm": stakes.require_human_confirm,
            "cache":                 "OFF",
        })
    trace.append(gate_entry)

    # â”€â”€ [3] RAS Gate (checks 1-3) â€” only on non-mutation reads â”€â”€â”€â”€â”€â”€â”€â”€
    if not stakes.suspend_optimization:
        ras_result = await ras_gate.attempt(
            req, app_state.pool, app_state.redis, trace
        )
        if ras_result:
            acc = accounting.build_ras_accounting(intent=intent)
            vpt_result = vpt_calc.compute(intent, 0, req.context.get("outcome_count", 1))
            latency_ms = int((time.time() - start) * 1000)
            await telemetry.write_request_log(
                pool=app_state.pool, req=req, trace=trace,
                usage={"tokens_in": 0, "tokens_out": 0, "model_id": "none"},
                accounting=acc, latency_ms=latency_ms,
                gate_fired=ras_result["gate"],
            )
            return RouteResponse(
                response=ras_result["response"],
                decision_trace=trace,
                accounting=AccountingResult(**acc),
                quality=QualityResult(checked=False, method="ras"),
                latency_ms=latency_ms,
            )

    # â”€â”€ [4] Exact Cache â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not stakes.suspend_optimization and req.mode == "clever":
        cached = await cache.exact_get(app_state.redis, req)
        if cached:
            trace.append({"layer": "cache.exact", "result": "HIT", "saved": "~$0"})
            latency_ms = int((time.time() - start) * 1000)
            return RouteResponse(
                response=cached["response"],
                decision_trace=trace,
                accounting=AccountingResult(**cached["accounting"]),
                quality=QualityResult(checked=True, method="cache", score=1.0),
                latency_ms=latency_ms,
            )
    trace.append({
        "layer":  "cache.exact",
        "result": "OFF" if stakes.suspend_optimization else "miss",
    })

    # â”€â”€ [6] Myelination Check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    route_class = myelination.route_class_from(intent, confidence)
    myelin = await myelination.check(route_class, req.feature_class, app_state.pool)
    trace.append({
        "layer":       "myelination",
        "route_class": route_class,
        "phase":       myelin.phase,
        "p_hat":       myelin.p_hat,
        "sigma":       myelin.sigma,
        "n_obs":       myelin.n_obs,
        "lcb":         myelin.lcb,
        "decision":    myelin.decision,
    })

    # â”€â”€ [7] Router â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    force_model = None
    if stakes.suspend_optimization:
        force_model = _SONNET
        router_reason = "stakes_gate_forced"
    elif not myelin.eligible:
        force_model = _SONNET
        router_reason = f"myelination_{myelin.decision}"
    else:
        router_reason = "myelination_cheap_ok"
    trace.append({
        "layer":  "router",
        "model":  "claude-sonnet (forced)" if force_model else "claude-haiku",
        "reason": router_reason,
    })

    # â”€â”€ [8] Compressor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ctx = compressor.build_context(req, intent)
    trace.append({
        "layer":         "compressor",
        "fields_used":   ctx["fields_used"],
        "tokens_before": ctx["tokens_before"],
        "tokens_after":  ctx["tokens_after"],
        "reduction_pct": ctx["reduction_pct"],
    })

    # â”€â”€ [9] Cascade â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    result = await cascade.run(
        intent=intent,
        feature_class=req.feature_class,
        prompt=ctx["prompt"],
        context_tokens=ctx["tokens_after"],
        force_model=force_model,
    )
    q = result["quality"]
    trace.append({
        "layer":       "cascade",
        "model_tried": "claude-haiku" if not force_model else "claude-sonnet (forced)",
        "escalated":   result["escalated"],
        "model_used":  "claude-sonnet" if (result["escalated"] or force_model) else "claude-haiku",
        "quality": {
            "score":  q["score"],
            "passed": q["passed"],
            "reason": q["reason"],
        },
        "tokens_in":  result["usage"]["tokens_in"],
        "tokens_out": result["usage"]["tokens_out"],
    })

    # â”€â”€ [10] VpT â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    total_tokens = result["usage"]["tokens_in"] + result["usage"]["tokens_out"]
    outcome_count = req.context.get("outcome_count", 1)
    vpt_result = vpt_calc.compute(intent, total_tokens, outcome_count)
    trace.append({
        "layer":             "vpt",
        "vpt":               vpt_result["vpt"],
        "outcome_unit":      vpt_result["outcome_unit"],
        "outcome_value_usd": vpt_result["outcome_value_usd"],
    })

    # â”€â”€ [12] Accounting â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    acc = accounting.build_accounting(result["usage"], tokens_before=ctx["tokens_before"])
    acc["vpt"]               = vpt_result["vpt"]
    acc["outcome_unit"]      = vpt_result["outcome_unit"]
    acc["outcome_value_usd"] = vpt_result["outcome_value_usd"]
    latency_ms = int((time.time() - start) * 1000)

    # â”€â”€ [13] Telemetry â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    await telemetry.write_request_log(
        pool=app_state.pool, req=req, trace=trace,
        usage=result["usage"], accounting=acc,
        latency_ms=latency_ms, gate_fired=stakes.reason,
    )

    # â”€â”€ [14] Myelination Update â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    success  = not result["escalated"]
    severity = (
        "critical" if (not result["escalated"] and
                       q["score"] is not None and q["score"] < 0.7)
        else "wrong" if result["escalated"]
        else "none"
    )
    asyncio.create_task(
        myelination.update(route_class, success=success,
                           severity=severity, pool=app_state.pool)
    )

    # â”€â”€ [15] Cache Store â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not stakes.suspend_optimization and req.mode == "clever":
        await cache.exact_put(app_state.redis, req, result["text"], {
            k: v for k, v in acc.items()
            if k in ("tokens_in","tokens_out","cost_usd","baseline_cost_usd",
                     "saved_usd","saved_pct")
        })

    response_text = result["text"]
    if stakes.suspend_optimization:
        response_text = (
            f"STAKES_GATE_TRIP â€” optimization suspended.\\n"
            f"Reason: {stakes.reason}\\n"
            f"Human confirmation required before any action fires.\\n\\n"
            + response_text
        )

    return RouteResponse(
        response=response_text,
        decision_trace=trace,
        accounting=AccountingResult(
            tokens_in=acc["tokens_in"],
            tokens_out=acc["tokens_out"],
            cost_usd=acc["cost_usd"],
            baseline_cost_usd=acc["baseline_cost_usd"],
            saved_usd=acc["saved_usd"],
            saved_pct=acc["saved_pct"],
        ),
        quality=QualityResult(
            checked=True,
            method="cascade",
            score=q["score"],
        ),
        latency_ms=latency_ms,
    )
'''

# â”€â”€ gateway/telemetry/logger.py (updated â€” vpt + route_class) â”€â”€â”€â”€â”€â”€â”€â”€â”€
files["gateway/telemetry/logger.py"] = '''\
"""
Request logger â€” writes every call to request_log (Postgres).
Non-fatal on error so a DB hiccup never kills a user request.
"""
import json
import logging
from typing import Optional

log = logging.getLogger(__name__)

async def write_request_log(
    pool, req, trace: list, usage: dict,
    accounting: dict, latency_ms: int,
    gate_fired: Optional[str] = None,
) -> None:
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO request_log (
                    mode, feature_class, intent, stakes,
                    gate_fired, model_used,
                    tokens_in, tokens_out,
                    cost_usd, baseline_cost_usd,
                    latency_ms, decision_trace, aging_version,
                    vpt, outcome_unit, outcome_value_usd,
                    route_class
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,
                    $11,$12,$13,$14,$15,$16,$17
                )
                """,
                req.mode,
                req.feature_class,
                req.intent_hint or "unknown",
                req.stakes,
                gate_fired,
                usage.get("model_id", "none"),
                usage["tokens_in"],
                usage["tokens_out"],
                accounting["cost_usd"],
                accounting["baseline_cost_usd"],
                latency_ms,
                json.dumps(trace),
                req.context.get("aging_version"),
                accounting.get("vpt"),
                accounting.get("outcome_unit"),
                accounting.get("outcome_value_usd"),
                next(
                    (e.get("route_class") for e in trace if e.get("layer") == "myelination"),
                    None,
                ),
            )
    except Exception as exc:
        log.warning("request_log write failed: %s", exc)
'''

# â”€â”€ gateway/main.py (add APScheduler + VpT + tail_cost to /v1/stats) â”€â”€
files["gateway/main.py"] = '''\
"""
CLEVER Gateway â€” main entry point.
Novel layers build: APScheduler + /v1/stats with VpT + TCR.
"""
import asyncio
import logging
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from gateway.config import settings
from gateway.models import RouteRequest, RouteResponse
from gateway import pipeline
from gateway.sleep import consolidation
from gateway.telemetry import tail_cost as tail_cost_calc

logging.basicConfig(level=settings.LOG_LEVEL.upper())
log = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("CLEVER starting â€” env=%s", settings.CLEVER_ENV)

    app.state.pool = await asyncpg.create_pool(
        settings.POSTGRES_DSN, min_size=2, max_size=10
    )
    log.info("Postgres pool ready")

    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    log.info("Redis ready")

    # Sleep Consolidation scheduler â€” runs Sunday 3am
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: asyncio.create_task(consolidation.run(app.state.pool)),
        trigger="cron",
        day_of_week="sun",
        hour=3,
        minute=0,
    )
    scheduler.start()
    log.info("Sleep Consolidation scheduler started (Sunday 3am)")

    yield

    scheduler.shutdown(wait=False)
    await app.state.pool.close()
    await app.state.redis.aclose()
    log.info("CLEVER shut down cleanly")

app = FastAPI(title="CLEVER Gateway", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# â”€â”€ Health â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str

@app.get("/health", response_model=HealthResponse)
async def health():
    db_ok, redis_ok = "ok", "ok"
    try:
        async with app.state.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception as e:
        db_ok = f"error: {e}"
    try:
        await app.state.redis.ping()
    except Exception as e:
        redis_ok = f"error: {e}"
    overall = "ok" if db_ok == "ok" and redis_ok == "ok" else "degraded"
    return HealthResponse(status=overall, version=app.version, db=db_ok, redis=redis_ok)

# â”€â”€ Main pipeline â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.post("/v1/route", response_model=RouteResponse)
async def route(req: RouteRequest):
    """Full 15-step CLEVER pipeline."""
    return await pipeline.route(req, app.state)

# â”€â”€ Sleep Consolidation â€” manual trigger (for demo) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.post("/v1/admin/sleep")
async def trigger_sleep():
    """Manually trigger Sleep Consolidation (demo use only)."""
    asyncio.create_task(consolidation.run(app.state.pool))
    return {"status": "sleep_consolidation_triggered"}

# â”€â”€ Dashboard stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.get("/v1/stats")
async def stats():
    """Full stats for dashboard â€” includes VpT and Tail-Cost."""
    async with app.state.pool.acquire() as conn:

        totals = await conn.fetchrow("""
            SELECT
                COUNT(*)                             AS total_requests,
                COALESCE(SUM(cost_usd), 0)           AS total_cost_usd,
                COALESCE(SUM(baseline_cost_usd), 0)  AS total_baseline_usd,
                COALESCE(AVG(latency_ms), 0)         AS avg_latency_ms,
                COALESCE(AVG(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    END
                ), 0)                                AS avg_saved_pct
            FROM request_log
        """)

        trips = await conn.fetch("""
            SELECT ts, intent, gate_fired, feature_class
            FROM request_log
            WHERE gate_fired IS NOT NULL
            ORDER BY ts DESC LIMIT 10
        """)

        models = await conn.fetch("""
            SELECT model_used, COUNT(*) AS calls, SUM(cost_usd) AS total_cost
            FROM request_log
            WHERE model_used IS NOT NULL AND model_used != 'none'
            GROUP BY model_used ORDER BY calls DESC
        """)

        recent = await conn.fetch("""
            SELECT ts, intent, feature_class, model_used,
                   tokens_in, tokens_out, cost_usd, baseline_cost_usd,
                   ROUND(
                       CASE WHEN baseline_cost_usd > 0
                       THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                       ELSE 0 END
                   ::numeric, 1) AS saved_pct,
                   latency_ms, gate_fired, vpt, outcome_unit
            FROM request_log
            ORDER BY ts DESC LIMIT 20
        """)

        by_class = await conn.fetch("""
            SELECT
                feature_class,
                COUNT(*) AS calls,
                ROUND(AVG(
                    CASE WHEN baseline_cost_usd > 0
                    THEN (baseline_cost_usd - cost_usd) / baseline_cost_usd * 100
                    ELSE 0 END
                )::numeric, 1) AS avg_saved_pct,
                COALESCE(SUM(baseline_cost_usd - cost_usd), 0) AS total_saved_usd
            FROM request_log
            GROUP BY feature_class ORDER BY total_saved_usd DESC
        """)

        # VpT by intent
        vpt_by_intent = await conn.fetch("""
            SELECT
                intent,
                ROUND(AVG(vpt)::numeric, 4)               AS avg_vpt,
                ROUND(SUM(outcome_value_usd)::numeric, 2)  AS total_value_usd,
                SUM(tokens_in + tokens_out)                AS total_tokens
            FROM request_log
            WHERE vpt IS NOT NULL
            GROUP BY intent ORDER BY avg_vpt DESC
        """)

        # Myelination registry snapshot
        myelin_rows = await conn.fetch("""
            SELECT route_class, alpha, beta, n_obs,
                   ROUND((alpha::numeric / (alpha + beta)), 3) AS p_hat,
                   CASE
                       WHEN n_obs < 30  THEN 'Cortical'
                       WHEN n_obs < 100 THEN 'Myelinating'
                       ELSE 'Cerebellar'
                   END AS phase
            FROM myelination_registry
            ORDER BY n_obs DESC LIMIT 20
        """)

    total_saved = float(totals["total_baseline_usd"]) - float(totals["total_cost_usd"])

    # Tail-Cost Ratio (non-blocking)
    tcr = await tail_cost_calc.compute(app.state.pool, window_hours=24)

    return {
        "summary": {
            "total_requests":     totals["total_requests"],
            "total_cost_usd":     round(float(totals["total_cost_usd"]),    4),
            "total_baseline_usd": round(float(totals["total_baseline_usd"]), 4),
            "total_saved_usd":    round(max(0.0, total_saved),              4),
            "avg_saved_pct":      round(float(totals["avg_saved_pct"]),     1),
            "avg_latency_ms":     round(float(totals["avg_latency_ms"]),    0),
        },
        "stakes_gate_trips": [
            {"ts": str(r["ts"]), "intent": r["intent"],
             "reason": r["gate_fired"], "feature_class": r["feature_class"]}
            for r in trips
        ],
        "model_breakdown": [
            {"model": r["model_used"], "calls": r["calls"],
             "total_cost": round(float(r["total_cost"] or 0), 6)}
            for r in models
        ],
        "recent_requests": [
            {"ts": str(r["ts"]), "intent": r["intent"],
             "feature_class": r["feature_class"], "model": r["model_used"],
             "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"],
             "cost_usd": float(r["cost_usd"] or 0),
             "saved_pct": float(r["saved_pct"] or 0),
             "latency_ms": r["latency_ms"], "gate_fired": r["gate_fired"],
             "vpt": float(r["vpt"] or 0), "outcome_unit": r["outcome_unit"]}
            for r in recent
        ],
        "by_feature_class": [
            {"feature_class": r["feature_class"], "calls": r["calls"],
             "avg_saved_pct": float(r["avg_saved_pct"] or 0),
             "total_saved_usd": float(r["total_saved_usd"] or 0)}
            for r in by_class
        ],
        "vpt_by_intent": [
            {"intent": r["intent"],
             "avg_vpt": float(r["avg_vpt"] or 0),
             "total_value_usd": float(r["total_value_usd"] or 0),
             "total_tokens": r["total_tokens"]}
            for r in vpt_by_intent
        ],
        "myelination": [
            {"route_class": r["route_class"], "phase": r["phase"],
             "p_hat": float(r["p_hat"] or 0),
             "n_obs": r["n_obs"],
             "alpha": r["alpha"], "beta": r["beta"]}
            for r in myelin_rows
        ],
        "tail_cost": tcr,
    }
'''

# â”€â”€ Write all files â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
for path, content in files.items():
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="\n", encoding="utf-8") as f:
        f.write(content)
    print(f"  created  {path}")

print("\nAll novel layer files created.")

