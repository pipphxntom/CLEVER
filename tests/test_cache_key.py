from gateway.layers.cache import make_key, canonical_context


def test_different_accounts_different_keys():
    k1 = make_key("balance?", "triage", "collections_outreach", "v1", {"account": "1"})
    k2 = make_key("balance?", "triage", "collections_outreach", "v1", {"account": "2"})
    assert k1 != k2


def test_same_payload_same_key():
    k1 = make_key("Balance?", "triage", "collections_outreach", "v1", {"account": "1"})
    k2 = make_key("balance?", "triage", "collections_outreach", "v1", {"account": "1"})
    assert k1 == k2


def test_version_scopes_keys():
    a = make_key("q", "triage", "fc", "v1", {})
    b = make_key("q", "triage", "fc", "v2", {})
    assert a != b


def test_canonical_projects_fields():
    ctx = canonical_context({"account": "1", "noise": "x"}, ["account", "balance"])
    assert ctx == {"account": "1"}
