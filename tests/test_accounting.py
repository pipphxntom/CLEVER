from gateway.telemetry import accounting


def test_two_legs_sum():
    legs = [
        {"tier": "cheap", "tokens_in": 100, "tokens_out": 50},
        {"tier": "strong", "tokens_in": 100, "tokens_out": 80},
    ]
    acc = accounting.build_accounting(legs, tokens_before=500)
    cheap = accounting.cost_of(100, 50, "cheap")
    strong = accounting.cost_of(100, 80, "strong")
    assert acc["cost_usd"] == round(cheap + strong, 6)
    assert acc["tokens_in"] == 200
    assert acc["tokens_out"] == 130


def test_ras_zero_actual():
    acc = accounting.build_zero_cost_accounting(tokens_before=40, intent="triage")
    assert acc["cost_usd"] == 0.0
    assert acc["tokens_in"] == 0
    assert acc["saved_pct"] == 100.0
    assert acc["baseline_cost_usd"] > 0


def test_cache_hit_zero_actual():
    acc = accounting.cache_hit_accounting(0.0123)
    assert acc["cost_usd"] == 0.0
    assert acc["cache_hit"] is True
    assert acc["saved_usd"] == 0.0123
