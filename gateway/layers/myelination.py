"""Per-route cheap-tier eligibility.

Cold start used to force-strong AND skip updates → cheap never ran (deadlock).
Now: strong quality-checked calls increment n_obs only. After N_MIN, cheap is
explored for N_EXPLORE trials, then LCB gates.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from gateway import catalog
from gateway.config import settings

log = logging.getLogger(__name__)

Z = 1.645


@dataclass
class MyelinDecision:
    eligible: bool
    phase: str
    p_hat: float
    sigma: float
    n_obs: int
    lcb: float
    decision: str
    alpha: float = 1.0
    beta: float = 1.0
    cheap_trials: int = 0


def phase_of(n_obs: int, cheap_trials: int = 0) -> str:
    if n_obs < settings.N_MIN:
        return "cold"
    if cheap_trials < settings.N_EXPLORE:
        return "explore"
    if n_obs < 100:
        return "warming"
    return "stable"


def wilson_lcb(successes: float, n: int) -> float:
    if n <= 0:
        return 0.0
    p = max(0.0, min(1.0, successes / n))
    z = Z
    denom = 1.0 + (z * z) / n
    centre = p + (z * z) / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * n)) / n)
    lcb = (centre - margin) / denom
    return max(0.0, min(1.0, lcb))


def cheap_trials_of(alpha: float, beta: float) -> int:
    return max(0, int(round((alpha - 1) + (beta - 1))))


def decision_from_stats(alpha: float, beta: float, n_obs: int, tau: float) -> MyelinDecision:
    successes = max(0.0, alpha - 1.0)
    cheap_trials = cheap_trials_of(alpha, beta)
    n_cheap = max(cheap_trials, 0)
    p_hat = alpha / (alpha + beta) if (alpha + beta) else 0.5
    var = (alpha * beta) / ((alpha + beta) ** 2 * (alpha + beta + 1)) if (alpha + beta) > 0 else 0.25
    sigma = math.sqrt(max(0.0, var))
    lcb = wilson_lcb(successes, n_cheap) if n_cheap > 0 else 0.0
    phase = phase_of(n_obs, cheap_trials)

    if n_obs < settings.N_MIN:
        eligible, decision = False, "cold_start"
    elif cheap_trials < settings.N_EXPLORE:
        eligible, decision = True, "explore"
    elif lcb >= tau:
        eligible, decision = True, "cheap_ok"
    else:
        eligible, decision = False, "cheap_ineligible"

    return MyelinDecision(
        eligible=eligible,
        phase=phase,
        p_hat=round(p_hat, 4),
        sigma=round(sigma, 4),
        n_obs=n_obs,
        lcb=round(lcb, 4),
        decision=decision,
        alpha=alpha,
        beta=beta,
        cheap_trials=cheap_trials,
    )


async def check(route_class: str, feature_class: str, pool) -> MyelinDecision:
    tau = catalog.q_floor(feature_class)
    if pool is None:
        return decision_from_stats(1, 1, 0, tau)
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT alpha, beta, n_obs, "
                "COALESCE(cheap_n, GREATEST(alpha+beta-2,0)) AS cheap_n "
                "FROM myelination_registry WHERE route_class = $1",
                route_class,
            )
    except Exception as exc:
        log.warning("myelination.check error: %s", exc)
        return decision_from_stats(1, 1, 0, tau)
    if not row:
        return decision_from_stats(1, 1, 0, tau)
    d = decision_from_stats(row["alpha"], row["beta"], row["n_obs"], tau)
    if row.get("cheap_n") is not None:
        d.cheap_trials = int(row["cheap_n"])
        if d.n_obs >= settings.N_MIN and d.cheap_trials < settings.N_EXPLORE:
            d.eligible, d.decision, d.phase = True, "explore", "explore"
        elif d.n_obs >= settings.N_MIN and d.cheap_trials >= settings.N_EXPLORE:
            pass  # LCB already applied using alpha/beta
    return d


async def update(
    route_class: str,
    *,
    cheap_tried: bool,
    success: bool,
    severity: str,
    pool,
    count_strong_obs: bool = False,
) -> None:
    """cheap_tried updates alpha/beta. Strong-only cold traffic increments n_obs only."""
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
                log.warning("route_reset route_class=%s severity=critical", route_class)
                return

            if cheap_tried and success:
                await conn.execute(
                    """
                    INSERT INTO myelination_registry
                        (route_class, alpha, beta, n_obs, cheap_n, updated_at)
                    VALUES ($1, 2, 1, 1, 1, now())
                    ON CONFLICT (route_class) DO UPDATE
                    SET alpha = myelination_registry.alpha + 1,
                        n_obs = myelination_registry.n_obs + 1,
                        cheap_n = COALESCE(myelination_registry.cheap_n, 0) + 1,
                        updated_at = now()
                    """,
                    route_class,
                )
                return

            if cheap_tried and not success:
                await conn.execute(
                    """
                    INSERT INTO myelination_registry
                        (route_class, alpha, beta, n_obs, cheap_n, last_correction, updated_at)
                    VALUES ($1, 1, 2, 1, 1, now(), now())
                    ON CONFLICT (route_class) DO UPDATE
                    SET beta = myelination_registry.beta + 1,
                        n_obs = myelination_registry.n_obs + 1,
                        cheap_n = COALESCE(myelination_registry.cheap_n, 0) + 1,
                        last_correction = now(),
                        updated_at = now()
                    """,
                    route_class,
                )
                return

            if count_strong_obs:
                await conn.execute(
                    """
                    INSERT INTO myelination_registry
                        (route_class, alpha, beta, n_obs, updated_at)
                    VALUES ($1, 1, 1, 1, now())
                    ON CONFLICT (route_class) DO UPDATE
                    SET n_obs = myelination_registry.n_obs + 1,
                        updated_at = now()
                    """,
                    route_class,
                )
    except Exception as exc:
        log.warning("myelination.update error: %s", exc)


def route_class_from(intent: str, confidence: float) -> str:
    complexity = "high" if confidence < 0.8 else "standard"
    return f"{intent}:{complexity}"
