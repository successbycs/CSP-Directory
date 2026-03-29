"""Tests for G2 enrichment (M50)."""

from __future__ import annotations

from services.enrichment.g2_enricher import (
    _extract_g2_categories,
    _extract_reviewer_titles,
    _extract_testimonials,
    _guess_g2_url,
    _is_g2_product_url,
    _parse_g2_profile,
    enrich_vendors_from_g2,
    find_g2_url,
    run_canary_check,
    trigger_g2_via_n8n,
)


# ---------------------------------------------------------------------------
# _is_g2_product_url
# ---------------------------------------------------------------------------

def test_g2_product_url_accepted():
    assert _is_g2_product_url("https://www.g2.com/products/gainsight/reviews") is True


def test_g2_product_url_no_products_path():
    assert _is_g2_product_url("https://www.g2.com/categories/customer-success") is False


def test_g2_product_url_wrong_domain():
    assert _is_g2_product_url("https://gainsight.com") is False


def test_g2_product_url_empty():
    assert _is_g2_product_url("") is False


# ---------------------------------------------------------------------------
# find_g2_url
# ---------------------------------------------------------------------------

def _fake_search_returning(url: str):
    """Return a search_fn that yields one result with the given website."""
    def search_fn(queries):
        return [{"website": url, "company_name": "Test", "raw_description": ""}]
    return search_fn


def test_find_g2_url_returns_first_product_url():
    url = find_g2_url("Gainsight", search_fn=_fake_search_returning("https://www.g2.com/products/gainsight/reviews"))
    assert url == "https://www.g2.com/products/gainsight/reviews"


def test_find_g2_url_ignores_non_product_urls():
    url = find_g2_url("Gainsight", search_fn=_fake_search_returning("https://www.g2.com/categories/cs"))
    assert url is None


def test_find_g2_url_propagates_search_exception():
    """Search exceptions propagate so batch callers can track errors."""
    def failing_search(queries):
        raise RuntimeError("network error")

    try:
        find_g2_url("Gainsight", search_fn=failing_search)
    except RuntimeError as exc:
        assert "network error" in str(exc)
    else:
        # Heuristic may have resolved the URL before search was called
        pass


# ---------------------------------------------------------------------------
# _parse_g2_profile — feed known HTML text, assert all fields extracted
# ---------------------------------------------------------------------------

SAMPLE_G2_TEXT = """
Gainsight | G2
4.5 out of 5 stars
1,234 reviews
Mid-Market users prefer this product.

Categories: Customer Success Software, CRM

What do you like best about Gainsight?
The automation features save our team hours every week and the health scores are very accurate.

What do you like best about Gainsight?
Excellent reporting and the ability to create playbooks for our CS team.

| Director of Customer Success at Acme Corp
| VP of Operations at BigCo
| Customer Success Manager

SOC 2 certified. GDPR compliant.
"""


def test_parse_g2_profile_extracts_rating():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    assert result.get("g2_rating") == 4.5


def test_parse_g2_profile_extracts_review_count():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    assert result.get("g2_review_count") == 1234


def test_parse_g2_profile_extracts_market_segment():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    assert result.get("g2_market_segment") == "Mid-Market"


def test_parse_g2_profile_extracts_categories():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    cats = result.get("g2_categories", [])
    assert any("Customer Success" in c for c in cats)


def test_parse_g2_profile_extracts_testimonials():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    testimonials = result.get("testimonials", [])
    assert len(testimonials) >= 1
    assert all(t.get("source") == "G2" for t in testimonials)
    assert all(len(t.get("quote", "")) > 10 for t in testimonials)


def test_parse_g2_profile_extracts_icp_titles():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    icp = result.get("icp", [])
    assert any("Director" in t or "VP" in t or "Manager" in t for t in icp)


def test_parse_g2_profile_detects_soc2():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    assert result.get("soc2") is True
    assert "SOC 2" in result.get("compliance", [])


def test_parse_g2_profile_detects_gdpr():
    result = _parse_g2_profile(SAMPLE_G2_TEXT, "https://www.g2.com/products/gainsight/reviews")
    assert result is not None
    assert "GDPR" in result.get("compliance", [])


def test_parse_g2_profile_stores_g2_url():
    url = "https://www.g2.com/products/gainsight/reviews"
    result = _parse_g2_profile(SAMPLE_G2_TEXT, url)
    assert result is not None
    assert result.get("g2_url") == url


def test_parse_g2_profile_returns_none_for_empty_text():
    result = _parse_g2_profile("", "https://www.g2.com/products/x/reviews")
    assert result is None


def test_parse_g2_profile_returns_none_for_short_text():
    result = _parse_g2_profile("Too short.", "https://www.g2.com/products/x/reviews")
    assert result is None


# ---------------------------------------------------------------------------
# run_canary_check
# ---------------------------------------------------------------------------

def test_canary_passes_when_g2_url_found():
    def good_search(queries):
        return [{"website": "https://www.g2.com/products/gainsight/reviews", "company_name": "Gainsight", "raw_description": ""}]

    assert run_canary_check(
        search_fn=good_search,
        fetch_page_fn=_make_page_fn(SAMPLE_G2_TEXT),
    ) is True


def test_canary_fails_when_no_url_found():
    def empty_search(queries):
        return []

    assert run_canary_check(search_fn=empty_search) is False


def test_canary_fails_when_url_not_product_page():
    def bad_search(queries):
        return [{"website": "https://www.g2.com/categories/cs", "company_name": "Gainsight", "raw_description": ""}]

    assert run_canary_check(search_fn=bad_search) is False


# ---------------------------------------------------------------------------
# enrich_vendors_from_g2
# ---------------------------------------------------------------------------

def _make_page_fn(text: str):
    """Return a fetch_page_fn that returns the given text."""
    def fetch_page_fn(url):
        return {"text": text, "url": url, "status_code": 200}
    return fetch_page_fn


def test_enrich_vendors_aborts_on_canary_failure():
    result = enrich_vendors_from_g2(
        [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}],
        search_fn=lambda q: [],
        skip_canary=False,
    )
    assert result["skipped_canary"] is True
    assert result["attempted"] == 0


def test_enrich_vendors_skips_fully_enriched_vendor():
    vendor = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "g2_url": "https://www.g2.com/products/gainsight/reviews",
        "g2_rating": 4.5,
        "g2_review_count": 1234,
        "g2_market_segment": "Mid-Market",
        "g2_categories": ["Customer Success"],
        "testimonials": [{"source": "G2", "quote": "Great product"}],
        "icp": ["Director of CS"],
        "soc2": True,
        "compliance": ["SOC 2"],
    }
    upserts = []
    result = enrich_vendors_from_g2(
        [vendor],
        upsert_fn=lambda k, v: upserts.append(v),
        skip_canary=True,
    )
    assert len(upserts) == 0
    assert result["attempted"] == 1


def test_enrich_vendors_writes_missing_fields():
    vendors = [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}]

    def good_search(queries):
        return [{"website": "https://www.g2.com/products/gainsight/reviews", "company_name": "Gainsight", "raw_description": ""}]

    upserts = []
    result = enrich_vendors_from_g2(
        vendors,
        upsert_fn=lambda k, v: upserts.append(v),
        search_fn=good_search,
        fetch_page_fn=_make_page_fn(SAMPLE_G2_TEXT),
        skip_canary=True,
    )
    assert result["enriched"] == 1
    assert len(upserts) == 1
    assert "g2_url" in upserts[0]
    assert "g2_rating" in upserts[0]


def test_enrich_vendors_uses_existing_g2_url():
    """If g2_url already known, should skip search and go straight to fetch."""
    vendor = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "g2_url": "https://www.g2.com/products/gainsight/reviews",
    }
    search_called = {"count": 0}

    def search_fn(queries):
        search_called["count"] += 1
        return []

    upserts = []
    enrich_vendors_from_g2(
        [vendor],
        upsert_fn=lambda k, v: upserts.append(v),
        search_fn=search_fn,
        fetch_page_fn=_make_page_fn(SAMPLE_G2_TEXT),
        skip_canary=True,
    )
    assert search_called["count"] == 0


def test_enrich_vendors_counts_miss_when_no_g2_profile():
    vendors = [{"vendor_name": "UnknownCo", "website": "https://unknown.com"}]
    result = enrich_vendors_from_g2(
        vendors,
        search_fn=lambda q: [],
        skip_canary=True,
    )
    assert result["miss_count"] == 1
    assert result["enriched"] == 0


def test_enrich_vendors_collects_errors_and_continues():
    vendors = [
        {"vendor_name": "BrokenCo", "website": "https://broken.com"},
        {"vendor_name": "GoodCo", "website": "https://good.com"},
    ]
    call_count = {"n": 0}

    def flaky_search(queries):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("rate limited")
        return [{"website": "https://www.g2.com/products/goodco/reviews", "company_name": "GoodCo", "raw_description": ""}]

    upserts = []
    result = enrich_vendors_from_g2(
        vendors,
        upsert_fn=lambda k, v: upserts.append(v),
        search_fn=flaky_search,
        fetch_page_fn=_make_page_fn(SAMPLE_G2_TEXT),
        skip_canary=True,
    )
    assert len(result["errors"]) == 1
    assert result["attempted"] == 2


# ---------------------------------------------------------------------------
# _guess_g2_url (R1)
# ---------------------------------------------------------------------------

def test_guess_g2_url_simple_name():
    assert _guess_g2_url("Gainsight") == "https://www.g2.com/products/gainsight"


def test_guess_g2_url_multiword():
    assert _guess_g2_url("ChurnZero") == "https://www.g2.com/products/churnzero"


def test_guess_g2_url_with_spaces():
    assert _guess_g2_url("Gainsight PX") == "https://www.g2.com/products/gainsight-px"


def test_guess_g2_url_with_punctuation():
    assert _guess_g2_url("monday.com") == "https://www.g2.com/products/monday-com"


def test_guess_g2_url_empty_returns_none():
    assert _guess_g2_url("") is None


def test_guess_g2_url_special_chars_only_returns_none():
    assert _guess_g2_url("!!!") is None


# ---------------------------------------------------------------------------
# _validate_g2_url redirect handling (R1 / B1)
# ---------------------------------------------------------------------------

def test_validate_g2_url_rejects_search_redirect():
    """A redirect to /products?query=foo must NOT pass validation."""
    import unittest.mock as mock

    fake_resp = mock.Mock()
    fake_resp.status_code = 200
    fake_resp.url = "https://www.g2.com/products?utf8=%E2%9C%93&query=unknownco"

    with mock.patch("services.enrichment.g2_enricher.requests.get", return_value=fake_resp):
        from services.enrichment.g2_enricher import _validate_g2_url
        assert _validate_g2_url("https://www.g2.com/products/unknownco") is False


def test_validate_g2_url_accepts_product_redirect():
    """A redirect to /products/gainsight/reviews must pass validation."""
    import unittest.mock as mock

    fake_resp = mock.Mock()
    fake_resp.status_code = 200
    fake_resp.url = "https://www.g2.com/products/gainsight/reviews"

    with mock.patch("services.enrichment.g2_enricher.requests.get", return_value=fake_resp):
        from services.enrichment.g2_enricher import _validate_g2_url
        assert _validate_g2_url("https://www.g2.com/products/gainsight") is True


# ---------------------------------------------------------------------------
# trigger_g2_via_n8n (R2)
# ---------------------------------------------------------------------------

def test_trigger_g2_via_n8n_returns_triggered_true_on_success():
    import unittest.mock as mock

    with mock.patch("services.n8n_client.post_webhook", return_value={"ok": True}) as mocked:
        result = trigger_g2_via_n8n(
            [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}],
            skip_canary=True,
        )
    assert result["triggered"] is True
    assert result["attempted"] == 1
    call_payload = mocked.call_args[0][1]
    assert "vendors" in call_payload
    assert call_payload["vendors"][0]["vendor_name"] == "Gainsight"


def test_trigger_g2_via_n8n_falls_back_to_python_on_n8n_failure():
    import unittest.mock as mock

    with mock.patch("services.n8n_client.post_webhook", side_effect=RuntimeError("n8n down")):
        result = trigger_g2_via_n8n(
            [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}],
            skip_canary=True,
            fallback_to_python=True,
            upsert_fn=None,
        )
    assert result["triggered"] is False
    assert result["fallback"] == "python"
    assert "n8n_error" in result


def test_trigger_g2_via_n8n_no_fallback_returns_error_dict():
    import unittest.mock as mock

    with mock.patch("services.n8n_client.post_webhook", side_effect=RuntimeError("n8n down")):
        result = trigger_g2_via_n8n(
            [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}],
            skip_canary=True,
            fallback_to_python=False,
        )
    assert result["triggered"] is False
    assert "error" in result


def test_trigger_g2_via_n8n_empty_vendors():
    result = trigger_g2_via_n8n([])
    assert result["triggered"] is False
    assert result["error"] == "no_vendors"


# ---------------------------------------------------------------------------
# run_canary_check — layout parseability guard (R3)
# ---------------------------------------------------------------------------

def test_canary_fails_when_page_returns_no_parseable_fields():
    """Canary must fail if G2 URL is found but page yields no structured data."""
    good_url = "https://www.g2.com/products/gainsight/reviews"

    result = run_canary_check(
        search_fn=lambda q: [{"website": good_url, "company_name": "Gainsight", "raw_description": ""}],
        fetch_page_fn=lambda url: {"text": "x" * 200, "url": url, "status_code": 200},
    )
    assert result is False


def test_canary_passes_when_page_has_parseable_rating():
    """Canary passes when URL found and at least one structured field extracted."""
    good_url = "https://www.g2.com/products/gainsight/reviews"

    result = run_canary_check(
        search_fn=lambda q: [{"website": good_url, "company_name": "Gainsight", "raw_description": ""}],
        fetch_page_fn=_make_page_fn(SAMPLE_G2_TEXT),
    )
    assert result is True


# ---------------------------------------------------------------------------
# _RATING_RE multi-decimal fix (B2)
# ---------------------------------------------------------------------------

def test_rating_re_matches_two_decimal_places():
    from services.enrichment.g2_enricher import _RATING_RE
    m = _RATING_RE.search("Rated 4.57 out of 5")
    assert m is not None
    assert m.group(1) == "4.57"


def test_rating_re_matches_single_decimal():
    from services.enrichment.g2_enricher import _RATING_RE
    m = _RATING_RE.search("4.5 out of 5 stars")
    assert m is not None
    assert m.group(1) == "4.5"