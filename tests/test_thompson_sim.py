"""Reproducible routing-cost comparison. No Docker, no API.

Cheap = 0.5, strong = 1.0, escalate = 1.5. τ = 0.92.
This is not a live savings number. It is the same math the research
handoff used to claim Thompson beats Wilson LCB at production N_MIN=30.
"""
from __future__ import annotations

import math
import random

from gateway.layers.myelination import thompson_decision, wilson_lcb


CHEAP_COST = 0.5
STRONG_COST = 1.0
ESCALATE_COST = 1.5
TAU = 0.92
Z = 1.645


def _lcb_decision(alpha, beta, n_obs, cheap_n, n_min=30, n_explore=10, tau=TAU):
    cheap_trials = cheap_n
    successes = max(0.0, alpha - 1.0)
    if n_obs < n_min:
        return False
    if cheap_trials < n_explore:
        return True
    lcb = wilson_lcb(successes, cheap_trials) if cheap_trials > 0 else 0.0
    return lcb >= tau


def _run(policy: str, n: int, true_p: float, seed: int, degrade_at=None, degrade_p=0.75):
    rng = random.Random(seed)
    alpha, beta, n_obs, cheap_n = 1.0, 1.0, 0, 0
    cost = 0.0
    cheap_finals = 0
    escalations = 0
    for i in range(n):
        p = degrade_p if (degrade_at is not None and i >= degrade_at) else true_p
        if policy == "lcb":
            use_cheap = _lcb_decision(alpha, beta, n_obs, cheap_n)
        else:
            d = thompson_decision(
                alpha, beta, n_obs, TAU,
                cheap_trials=cheap_n,
                cold_min=30,
                rng=random.Random(rng.randint(0, 2**31 - 1)),
            )
            use_cheap = d.eligible
        if not use_cheap:
            cost += STRONG_COST
            n_obs += 1
            continue
        if rng.random() < p:
            alpha += 1
            cheap_n += 1
            n_obs += 1
            cost += CHEAP_COST
            cheap_finals += 1
        else:
            beta += 1
            cheap_n += 1
            n_obs += 1
            cost += ESCALATE_COST
            escalations += 1
    all_strong = n * STRONG_COST
    saved = (all_strong - cost) / all_strong * 100.0
    return {
        "cost": cost,
        "saved_pct": saved,
        "cheap_finals": cheap_finals,
        "escalations": escalations,
    }


def test_thompson_saves_more_than_lcb_when_cheap_is_good():
    lcb = _run("lcb", 500, 0.96, seed=42)
    th = _run("thompson", 500, 0.96, seed=42)
    # LCB at N_MIN=30 / N_EXPLORE=10 barely unlocks. Thompson must beat it.
    assert lcb["saved_pct"] < 5.0
    assert th["saved_pct"] > 15.0
    assert th["cost"] < lcb["cost"]
    assert th["cheap_finals"] > lcb["cheap_finals"]


def test_thompson_self_corrects_when_cheap_is_bad():
    th = _run("thompson", 500, 0.50, seed=7)
    lcb = _run("lcb", 500, 0.50, seed=7)
    # Neither should print a fake win. Bad cheap ≈ all-strong.
    assert th["saved_pct"] < 8.0
    assert lcb["saved_pct"] < 8.0


def test_thompson_still_saves_after_degradation():
    """Mean over seeds. Seed 3 is a slow-explore draw (~5%); do not cherrypick."""
    th_pct, lcb_pct = [], []
    for seed in range(5):
        th_pct.append(
            _run("thompson", 500, 0.96, seed=seed, degrade_at=300, degrade_p=0.75)["saved_pct"]
        )
        lcb_pct.append(
            _run("lcb", 500, 0.96, seed=seed, degrade_at=300, degrade_p=0.75)["saved_pct"]
        )
    assert sum(th_pct) / len(th_pct) > 10.0
    assert sum(th_pct) / len(th_pct) > sum(lcb_pct) / len(lcb_pct)


def test_wilson_still_matches_known_n100():
    # Documented: 95/100 successes, LCB ≈ 0.9008 < 0.92
    lcb = wilson_lcb(95, 100)
    assert math.isclose(lcb, 0.9008, abs_tol=0.002)
    assert lcb < 0.92
