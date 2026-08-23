from gateway.layers.myelination import beta_credible
from gateway.sleep.consolidation import decay_alpha_beta, pattern_qualifies, run


def test_decay_reduces_confidence():
    bc_before = beta_credible(51, 3, 0.92)
    a_after, b_after = decay_alpha_beta(51, 3, 0.80)
    assert a_after == 41
    assert b_after == 3  # 1 + round((3-1)*0.80) = 3; α*0.80 rounding would have made 2 and raised P(p>τ)
    bc_after = beta_credible(a_after, b_after, 0.92)
    assert bc_after < bc_before


def test_decay_preserves_ratio():
    p_before = 51 / (51 + 3)
    a, b = decay_alpha_beta(51, 3, 0.80)
    p_after = a / (a + b)
    assert abs(p_before - p_after) < 0.05
    assert (a + b) < (51 + 3)


def test_decay_floor_is_one():
    assert decay_alpha_beta(1, 1, 0.80) == (1, 1)
    assert decay_alpha_beta(2, 1, 0.80)[0] >= 1
    assert decay_alpha_beta(2, 1, 0.80)[1] >= 1


def test_pattern_detection_requires_quality():
    assert pattern_qualifies(5, 0.70, 0.70, threshold=5, quality_floor=0.95) is False
    assert pattern_qualifies(5, 0.97, 0.90, threshold=5, quality_floor=0.95) is True
    assert pattern_qualifies(2, 0.99, 0.99, threshold=5, quality_floor=0.95) is False
    assert pattern_qualifies(5, 0.97, 0.80, threshold=5, quality_floor=0.95) is False


def test_decay_is_idempotent_on_ones():
    a, b = 1, 1
    for _ in range(5):
        a, b = decay_alpha_beta(a, b, 0.80)
    assert (a, b) == (1, 1)


async def test_sleep_no_pool_is_noop():
    out = await run(None, redis=None, trigger="manual")
    assert out["status"] == "no_pool"
    assert out["trigger"] == "manual"
