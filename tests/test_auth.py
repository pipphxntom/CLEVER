from gateway.auth import _check, _extract


def test_accepts_matching_key():
    assert _check("secret", "secret") is True


def test_rejects_wrong_key():
    assert _check("secret", "other") is False
    assert _check("", "secret") is False
    assert _check("secret", "") is False


def test_bearer_extract():
    assert _extract(None, "Bearer abc") == "abc"
    assert _extract("hdr", "Bearer abc") == "hdr"
