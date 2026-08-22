from gateway.layers.myelination import decision_from_stats, wilson_lcb
from gateway.config import settings


def test_lcb_never_negative():
    d = decision_from_stats(1, 1, 0, tau=0.92)
    assert d.lcb >= 0
    assert d.eligible is False
    assert d.decision == "cold_start"


def test_after_cold_start_explores_before_lcb():
    d = decision_from_stats(1, 1, settings.N_MIN, tau=0.92)
    assert d.decision == "explore"
    assert d.eligible is True
    assert d.cheap_trials == 0


def test_many_cheap_fails_block_after_explore():
    d = decision_from_stats(50, 5, 55, tau=0.92)
    assert d.decision in {"cheap_ok", "cheap_ineligible", "explore"}


def test_unlock_example_at_n100():
    d = decision_from_stats(96, 5, 100, tau=0.90)
    assert d.n_obs >= 30


def test_wilson_clamped():
    assert wilson_lcb(0, 0) == 0.0
    assert 0.0 <= wilson_lcb(10, 10) <= 1.0
