from gateway.layers import quality


def test_triage_canned_passes():
    text = (
        "Top overdue accounts: Account 4021 ($12,500, 45 days overdue), "
        "Account 3887 ($8,200, 32 days overdue), Account 5541 ($3,100, 28 days overdue)."
    )
    r = quality.score(text, "triage", "collections_outreach")
    assert r["passed"] is True
    assert r["score"] >= 0.92


def test_short_fails():
    r = quality.score("no", "email_draft", "collections_outreach")
    assert r["passed"] is False


def test_strong_unscored():
    r = quality.unchecked_strong()
    assert r["score"] is None
    assert r["method"] == "unchecked_strong"
    assert r["passed"] is True


def test_no_mock_signal_check():
    text = "[MOCK] this string used to force escalate. " + ("word " * 40)
    r = quality.score(text, "notes", "collections_outreach")
    assert all(c["check"] != "mock_signal" for c in r["checks"])


def test_money_format_matches_integer_balance():
    text = (
        "Dear Ada Cole, account 40211 invoice INV-2024-089 has a balance of $12,500.00 "
        "that remains outstanding. Please arrange payment at your earliest convenience "
        "so we can update our records and close this collections item."
    )
    r = quality.score(
        text, "email_draft", "collections_outreach",
        context={"account": "40211", "contact": "Ada Cole", "balance": 12500, "invoice_ids": ["INV-2024-089"]},
    )
    assert r["passed"] is True, r


def test_missing_contact_fails_email():
    text = (
        "Dear Customer, please pay invoice as soon as possible. "
        "This is a collections follow-up regarding an outstanding balance on file."
    )
    r = quality.score(
        text, "email_draft", "collections_outreach",
        context={"account": "40211", "contact": "Ada Cole", "balance": 12500, "invoice_ids": ["INV-2024-089"]},
    )
    assert r["passed"] is False
    assert any(c["check"] == "required_fields" and not c["passed"] for c in r["checks"])
