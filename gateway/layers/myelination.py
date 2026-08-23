"""Per-route cheap-tier eligibility.

v0.5: Thompson Sampling + Bayesian credible lock-in/out. The Beta update
rule is unchanged from v0.4.0 (cheap success α+=1, fail β+=1, strong-only
increments n_obs). Wilson LCB is kept as a diagnostic field only.

Cold-start deadlock (v0.3) is still closed: strong quality-checked calls
increment n_obs. After COLD_MIN (= N_MIN), the first cheap trial is forced
so the posterior can leave Beta(1,1). After that, Thompson explores in
proportion to P(p > τ | α, β).

Do not lock out on a thin posterior: one cheap fail at Beta(1,2) would
otherwise freeze the route until a sleep reset that itself needs cheap
trials. Lock-out requires LOCK_OUT_MIN_CHEAP observations.
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Optional

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
    credible: float = 0.0
    thompson_sample: Optional[float] = None
    tau: float = 0.92


def _cold_min() -> int:
    cold = getattr(settings, "COLD_MIN", None)
    if cold is None:
        return int(settings.N_MIN)
    return int(cold)


def _lock_in() -> float:
    return float(getattr(settings, "LOCK_IN", 0.90))


def _lock_out() -> float:
    return float(getattr(settings, "LOCK_OUT", 0.01))


def _lock_out_min_cheap() -> int:
    return int(getattr(settings, "LOCK_OUT_MIN_CHEAP", 10))


def phase_of(n_obs: int, cheap_trials: int = 0) -> str:
    """n_obs label for dashboards/demos. Routing does not use this."""
    if n_obs < _cold_min():
        return "cold"
    if cheap_trials <= 0:
        return "explore"
    if n_obs < 100:
        return "warming"
    return "stable"


def wilson_lcb(successes: float, n: int) -> float:
    """Diagnostic only. Not the routing gate."""
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


def beta_credible(alpha: int, beta: int, tau: float) -> float:
    """P(p > tau | alpha, beta) for positive integer α, β.

    Beta-Binomial identity:
    P(p > τ | α, β) = P(X ≤ α-1 | X ~ Binomial(α+β-1, τ))

    α+β > 100 uses a normal approximation. Stdlib math only.
    """
    if tau <= 0:
        return 1.0
    if tau >= 1:
        return 0.0
    if alpha <= 0 or beta <= 0:
        return 0.0

    a = int(alpha)
    b = int(beta)
    if a + b > 100:
        p_hat = a / (a + b)
        var = (a * b) / ((a + b) ** 2 * (a + b + 1))
        sigma = math.sqrt(max(0.0, var))
        if sigma < 1e-10:
            return 1.0 if p_hat > tau else 0.0
        z = (p_hat - tau) / sigma
        return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))

    n = a + b - 1
    prob = 0.0
    log_tau = math.log(max(tau, 1e-15))
    log_1mtau = math.log(max(1.0 - tau, 1e-15))
    for k in range(a):
        log_term = (
            math.lgamma(n + 1)
            - math.lgamma(k + 1)
            - math.lgamma(n - k + 1)
            + k * log_tau
            + (n - k) * log_1mtau
        )
        prob += math.exp(log_term)
    return min(1.0, max(0.0, prob))


def thompson_decision(
    alpha: float,
    beta: float,
    n_obs: int,
    tau: float,
    cheap_trials: Optional[int] = None,
    cold_min: Optional[int] = None,
    lock_in: Optional[float] = None,
    lock_out: Optional[float] = None,
    lock_out_min: Optional[int] = None,
    rng: Optional[random.Random] = None,
) -> MyelinDecision:
    cold_min = _cold_min() if cold_min is None else int(cold_min)
    lock_in = _lock_in() if lock_in is None else float(lock_in)
    lock_out = _lock_out() if lock_out is None else float(lock_out)
    lock_out_min = _lock_out_min_cheap() if lock_out_min is None else int(lock_out_min)
    if cheap_trials is None:
        cheap_trials = cheap_trials_of(alpha, beta)
    cheap_trials = max(0, int(cheap_trials))

    a = max(1.0, float(alpha))
    b = max(1.0, float(beta))
    p_hat = a / (a + b)
    var = (a * b) / ((a + b) ** 2 * (a + b + 1))
    sigma = math.sqrt(max(0.0, var))
    successes = max(0.0, a - 1.0)
    lcb = wilson_lcb(successes, cheap_trials) if cheap_trials > 0 else 0.0

    def _base(**kwargs) -> MyelinDecision:
        fields = dict(
            eligible=False,
            phase="cold",
            p_hat=round(p_hat, 4),
            sigma=round(sigma, 4),
            n_obs=int(n_obs),
            lcb=round(lcb, 4),
            decision="cold_start",
            alpha=alpha,
            beta=beta,
            cheap_trials=cheap_trials,
            credible=0.0,
            thompson_sample=None,
            tau=tau,
        )
        fields.update(kwargs)
        return MyelinDecision(**fields)

    if n_obs < cold_min:
        return _base()

    # First cheap trial after cold. Beta(1,1) vs τ=0.92 samples above τ ~8%
    # of the time — without this force, cheap almost never runs (the same
    # class of deadlock v0.3.1 already had to close).
    if cheap_trials <= 0:
        return _base(
            eligible=True,
            phase="explore",
            decision="explore",
            credible=round(beta_credible(int(round(a)), int(round(b)), tau), 4),
        )

    credible = beta_credible(int(round(a)), int(round(b)), tau)

    if credible >= lock_in:
        return _base(
            eligible=True,
            phase="locked_cheap",
            decision="locked_cheap",
            credible=round(credible, 4),
        )

    if credible <= lock_out and cheap_trials >= lock_out_min:
        return _base(
            eligible=False,
            phase="locked_strong",
            decision="locked_strong",
            credible=round(credible, 4),
        )

    sampler = rng if rng is not None else random
    sample = sampler.betavariate(a, b)
    eligible = sample > tau
    return _base(
        eligible=eligible,
        phase="thompson",
        decision="cheap_explore" if eligible else "strong",
        credible=round(credible, 4),
        thompson_sample=round(sample, 4),
    )


def decision_from_stats(
    alpha: float,
    beta: float,
    n_obs: int,
    tau: float,
    cheap_trials: Optional[int] = None,
    **kwargs,
) -> MyelinDecision:
    """Public alias used by tests, demo, and the A–H harness."""
    return thompson_decision(
        alpha, beta, n_obs, tau, cheap_trials=cheap_trials, **kwargs
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
    cheap_n = int(row["cheap_n"]) if row["cheap_n"] is not None else None
    return decision_from_stats(
        row["alpha"], row["beta"], row["n_obs"], tau, cheap_trials=cheap_n
    )


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
                    SET alpha=1, beta=1, n_obs=0, cheap_n=0,
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
