from types import SimpleNamespace

from gateway.layers.semantic import context_hash


def test_different_accounts_different_hash():
    fields = ["account", "balance"]
    a = SimpleNamespace(query="draft email", feature_class="collections_outreach",
                        context={"account": "1", "balance": 10})
    b = SimpleNamespace(query="draft email", feature_class="collections_outreach",
                        context={"account": "2", "balance": 10})
    assert context_hash(a, fields) != context_hash(b, fields)


def test_same_account_same_hash():
    fields = ["account"]
    a = SimpleNamespace(query="x", feature_class="collections_outreach", context={"account": "1"})
    b = SimpleNamespace(query="y", feature_class="collections_outreach", context={"account": "1"})
    assert context_hash(a, fields) == context_hash(b, fields)
