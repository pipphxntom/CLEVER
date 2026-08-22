from types import SimpleNamespace

from gateway.layers import classifier


def _req(query, hint=None, feature_class="collections_outreach"):
    return SimpleNamespace(query=query, intent_hint=hint, feature_class=feature_class)


def test_keyword_triage():
    intent, conf, method = classifier.classify(_req("who owes us money"))
    assert intent == "triage"
    assert method == "keyword"
    assert conf == 0.8


def test_hint_used_when_known():
    intent, conf, method = classifier.classify(_req("hello", hint="inbox_check"))
    assert intent == "inbox_check"
    assert method == "config"
    assert conf == 1.0


def test_mutate_keyword_overrides_read_hint():
    intent, conf, method = classifier.classify(_req("please remit invoice 12", hint="triage"))
    assert intent == "remit"
    assert method == "keyword_mutate"


def test_campaign_send_is_mutate():
    intent, _, method = classifier.classify(_req("launch campaign to the list"))
    assert intent == "campaign_send"
    assert method == "keyword_mutate"


def test_write_a_is_email_draft():
    intent, _, method = classifier.classify(_req("Write a short collections dunning email"))
    assert intent == "email_draft"
    assert method in {"keyword", "keyword_mutate"}


def test_default_for_feature_class():
    intent, conf, method = classifier.classify(_req("hello there", feature_class="event_management"))
    assert intent == "event_summary"
    assert method == "default"
    assert conf == 0.5
