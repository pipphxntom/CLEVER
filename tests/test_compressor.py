from types import SimpleNamespace

from gateway.layers import compressor


def test_empty_context_zero_reduction():
    req = SimpleNamespace(query="who is overdue", context={})
    ctx = compressor.build_context(req, "triage")
    assert ctx["tokens_before"] == ctx["tokens_after"]
    assert ctx["reduction_pct"] == 0.0
    assert ctx["prompt"] == "who is overdue"


def test_projects_only_needed_fields():
    req = SimpleNamespace(
        query="who is overdue",
        context={"account": "4021", "balance": 12500, "noise": "DROP THIS", "days_overdue": 45, "status": "open"},
    )
    ctx = compressor.build_context(req, "triage")
    assert "noise" not in ctx["prompt"]
    assert "4021" in ctx["prompt"]
    assert ctx["tokens_after"] < ctx["tokens_before"]
    assert "noise" not in ctx["fields_used"]


def test_no_8200_constant():
    req = SimpleNamespace(query="hi", context={})
    ctx = compressor.build_context(req, "triage")
    assert ctx["tokens_before"] < 100
