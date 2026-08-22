from types import SimpleNamespace

from gateway.layers import stakes_gate


def _req(stakes="auto", feature_class="collections_outreach"):
    return SimpleNamespace(stakes=stakes, feature_class=feature_class)


def test_read_intent_not_suspended():
    r = stakes_gate.classify(_req(), "triage")
    assert r.suspend_optimization is False
    assert r.require_human_confirm is False


def test_remit_trips():
    r = stakes_gate.classify(_req(), "remit")
    assert r.suspend_optimization is True
    assert r.require_human_confirm is True
    assert "remit" in r.reason


def test_campaign_send_trips():
    r = stakes_gate.classify(_req(), "campaign_send")
    assert r.suspend_optimization is True


def test_explicit_mutate_flag():
    r = stakes_gate.classify(_req(stakes="mutate"), "triage")
    assert r.suspend_optimization is True
    assert r.reason == "explicit_mutate_flag"


def test_reconciliation_class_trips():
    r = stakes_gate.classify(_req(feature_class="reconciliation"), "triage")
    assert r.suspend_optimization is True
