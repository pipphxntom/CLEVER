from datetime import date, timedelta

from gateway.layers.ras import faq_match, structured_lookup, template_resolver


def test_invoice_not_parsed_as_year_account():
    hint = structured_lookup.attempt("what is the status of INV-2024-089")
    assert hint is not None
    assert hint["entity_type"] == "invoice"
    assert hint["entity_value"] == "INV-2024-089"


def test_account_five_digits():
    hint = structured_lookup.attempt("what is the balance on 40211")
    assert hint is not None
    assert hint["entity_type"] == "account"
    assert hint["entity_value"] == "40211"


def test_four_digit_year_alone_is_not_account():
    hint = structured_lookup.attempt("what is 2024")
    assert hint is None


def test_today_template():
    hit = template_resolver.attempt("what is today's date")
    assert hit is not None
    assert str(date.today().year) in hit["response"]


def test_days_until_uses_date_group():
    future = (date.today() + timedelta(days=10)).isoformat()
    hit = template_resolver.attempt(f"how many days until {future}")
    assert hit is not None
    assert "10 days" in hit["response"]


def test_faq_ranks_question_not_answer():
    entries = [
        {"id": 1, "question": "who handles disputes", "answer": "The AR team."},
        {"id": 2, "question": "what is the SLA", "answer": "disputes mentioned in passing here"},
    ]
    hit = faq_match.rank_faq("who handles disputes", entries, min_score=0.1)
    assert hit is not None
    assert hit["faq_id"] == 1


def test_faq_answer_only_word_does_not_hit():
    entries = [
        {"id": 1, "question": "office location", "answer": "disputes are handled in building B"},
    ]
    hit = faq_match.rank_faq("who handles disputes", entries, min_score=0.1)
    assert hit is None


def test_faq_does_not_steal_dunning_email():
    entries = [
        {"id": 1, "question": "what is the collections SLA", "answer": "Standard collections SLA is 30 days."},
        {"id": 2, "question": "who handles disputes", "answer": "The AR team."},
    ]
    hit = faq_match.rank_faq(
        "Write a short collections dunning email for this account",
        entries,
    )
    assert hit is None
