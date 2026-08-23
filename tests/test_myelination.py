import math
import random

from gateway.layers.myelination import (
    beta_credible,
    decision_from_stats,
    thompson_decision,
    wilson_lcb,
)
from gateway.config import settings


def test_lcb_never_negative():
    d = decision_from_stats(1, 1, 0, tau=0.92)
    assert d.lcb >= 0
    assert d.eligible is False
    assert d.decision == "cold_start"
    assert d.phase == "cold"


def test_after_cold_start_explores_before_lcb():
    """First cheap trial is forced. Beta(1,1) vs τ=0.92 would almost never sample."""
    d = decision_from_stats(1, 1, settings.N_MIN, tau=0.92)
    assert d.decision == "explore"
    assert d.eligible is True
    assert d.cheap_trials == 0


def test_cold_start_respects_cold_min_override():
    d = thompson_decision(1, 1, n_obs=9, tau=0.92, cold_min=10)
    assert d.decision == "cold_start"
    assert d.eligible is False
    d2 = thompson_decision(1, 1, n_obs=10, tau=0.92, cold_min=10)
    assert d2.decision == "explore"
    assert d2.eligible is True


def test_many_cheap_fails_do_not_lock_out_on_thin_data():
    """Beta(1,2) has P(p>0.92)≈0.006, below LOCK_OUT, but cheap_n=1 < min."""
    d = thompson_decision(1, 2, n_obs=31, tau=0.92, cheap_trials=1, lock_out_min=10)
    assert d.phase == "thompson"
    assert d.decision != "locked_strong"


def test_unlock_example_at_n100():
    d = decision_from_stats(96, 5, 100, tau=0.90)
    assert d.n_obs >= 30


def test_wilson_clamped():
    assert wilson_lcb(0, 0) == 0.0
    assert 0.0 <= wilson_lcb(10, 10) <= 1.0


def test_lock_in_deterministic():
    d = thompson_decision(99, 2, n_obs=100, tau=0.92, cheap_trials=99)
    assert d.decision == "locked_cheap"
    assert d.eligible is True
    assert d.credible >= 0.90
    assert d.thompson_sample is None


def test_lock_out_deterministic():
    d = thompson_decision(2, 20, n_obs=25, tau=0.92, cheap_trials=21, lock_out_min=10)
    assert d.decision == "locked_strong"
    assert d.eligible is False
    assert d.credible <= 0.01


def test_thompson_explores_after_cold():
    results = set()
    for i in range(200):
        d = thompson_decision(
            8, 1, n_obs=15, tau=0.92, cheap_trials=7, cold_min=5, rng=random.Random(i)
        )
        results.add(d.decision)
    assert "cheap_explore" in results
    assert "strong" in results


def test_beta_credible_edge_cases():
    assert beta_credible(1, 1, 0.92) < 0.10
    assert beta_credible(1, 1, 0.0) == 1.0
    assert beta_credible(1, 1, 1.0) == 0.0
    assert abs(beta_credible(1, 1, 0.92) - 0.08) < 1e-9
    assert 0.0 <= beta_credible(50, 50, 0.5) <= 1.0


def test_beta_credible_matches_monte_carlo():
    rng = random.Random(0)
    bc = beta_credible(51, 3, 0.92)
    hits = sum(1 for _ in range(20000) if rng.betavariate(51, 3) > 0.92)
    mc = hits / 20000
    assert abs(bc - mc) < 0.02


def test_beta_credible_lock_in_table():
    """8 successes, 0 fails → P(p>0.92) ~ 0.50 (handoff unlock table)."""
    # α = successes+1 = 9, β = 1
    assert abs(beta_credible(9, 1, 0.92) - (1.0 - 0.92**9)) < 1e-9
    assert 0.48 < beta_credible(9, 1, 0.92) < 0.53
    assert beta_credible(28, 1, 0.92) >= 0.90


def test_update_rule_fields_unchanged_on_decision():
    """Decision must not mutate α/β; those change only in myelination.update."""
    d = thompson_decision(6, 2, n_obs=20, tau=0.92, cheap_trials=6, cold_min=5)
    assert d.alpha == 6
    assert d.beta == 2
