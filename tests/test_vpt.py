from gateway.telemetry import vpt as vpt_calc


def test_zero_tokens_vpt_is_none():
    r = vpt_calc.compute("triage", 0, 1)
    assert r["vpt"] is None
    assert r["outcome_value_usd"] > 0


def test_positive_tokens_has_vpt():
    r = vpt_calc.compute("triage", 1000, 1)
    assert r["vpt"] is not None
    assert r["vpt"] > 0
