"""Tests for Tracxn teaser enrichment (M66)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.enrichment.tracxn_enricher import (
    derive_tracxn_slug,
    enrich_vendors_from_tracxn,
    fetch_tracxn_teaser,
    run_canary_check,
)


# ---------------------------------------------------------------------------
# derive_tracxn_slug
# ---------------------------------------------------------------------------


def test_derive_slug_from_website_domain():
    assert derive_tracxn_slug("Gainsight", "https://gainsight.com") == "gainsight"


def test_derive_slug_from_vendor_name_when_no_website():
    assert derive_tracxn_slug("ChurnZero") == "churnzero"


def test_derive_slug_strips_special_chars():
    assert derive_tracxn_slug("Staircase AI") == "staircase-ai"


def test_derive_slug_prefers_domain_over_name():
    assert derive_tracxn_slug("Example Corp", "https://www.vitally.io") == "vitally"


# ---------------------------------------------------------------------------
# fetch_tracxn_teaser
# ---------------------------------------------------------------------------


def _mock_response(html: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    return resp


SAMPLE_HTML = """
<html><body>
<script type="application/ld+json">
{"@type": "Organization", "address": {"addressLocality": "Austin", "addressRegion": "TX", "addressCountry": "US"}}
</script>
<p>Founded in 2014. Series B funding of $50M raised.</p>
<p>Total Funding: $75.3M. Headquarters: Austin, TX</p>
</body></html>
"""


def test_fetch_tracxn_teaser_parses_founded():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(SAMPLE_HTML))
    assert result is not None
    assert result.get("founded") == "2014"


def test_fetch_tracxn_teaser_parses_funding_stage():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(SAMPLE_HTML))
    assert result is not None
    assert "Series B" in result.get("funding_stage", "")


def test_fetch_tracxn_teaser_parses_total_funding():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(SAMPLE_HTML))
    assert result is not None
    # Regex finds first dollar amount in text; either value confirms extraction works
    assert result.get("total_funding", "").startswith("$")


def test_fetch_tracxn_teaser_parses_hq_from_json_ld():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response(SAMPLE_HTML))
    assert result is not None
    hq = result.get("hq_address", "")
    assert "Austin" in hq


def test_fetch_tracxn_teaser_returns_none_on_404():
    result = fetch_tracxn_teaser("unknownslug", request_get=lambda *a, **k: _mock_response("", 404))
    assert result is None


def test_fetch_tracxn_teaser_returns_none_on_network_error():
    import requests as req

    def fail(*a, **k):
        raise req.RequestException("timeout")

    result = fetch_tracxn_teaser("gainsight", request_get=fail)
    assert result is None


def test_fetch_tracxn_teaser_returns_none_for_empty_page():
    result = fetch_tracxn_teaser("gainsight", request_get=lambda *a, **k: _mock_response("<html></html>"))
    assert result is None


# ---------------------------------------------------------------------------
# run_canary_check
# ---------------------------------------------------------------------------


def test_canary_passes_when_data_returned():
    assert run_canary_check(request_get=lambda *a, **k: _mock_response(SAMPLE_HTML)) is True


def test_canary_fails_when_none_returned():
    assert run_canary_check(request_get=lambda *a, **k: _mock_response("", 404)) is False


# ---------------------------------------------------------------------------
# enrich_vendors_from_tracxn
# ---------------------------------------------------------------------------


def test_enrich_vendors_skips_canary_when_flag_set():
    """With skip_canary=True the batch proceeds even with a failing network."""
    vendors = [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}]
    canary_called = {"count": 0}

    def fake_get(url, **kwargs):
        if "gainsight" in url and canary_called["count"] == 0:
            canary_called["count"] += 1
            return _mock_response(SAMPLE_HTML)
        return _mock_response(SAMPLE_HTML)

    result = enrich_vendors_from_tracxn(vendors, request_get=fake_get, skip_canary=True)
    assert result["skipped_canary"] is False  # canary was skipped, not failed
    assert result["attempted"] == 1


def test_enrich_vendors_safe_upsert_skips_populated_fields():
    """Vendor with all fields already populated should be skipped entirely."""
    vendors = [{
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "founded": "2013",
        "hq_address": "San Francisco, CA",
        "funding_stage": "Series E",
        "total_funding": "$200M",
    }]
    upserts = []
    enrich_vendors_from_tracxn(vendors, upsert_fn=lambda k, v: upserts.append(v), skip_canary=True,
                                request_get=lambda *a, **k: _mock_response(SAMPLE_HTML))
    assert len(upserts) == 0


def test_enrich_vendors_writes_only_empty_fields():
    """Only null/empty fields get written; populated ones are preserved."""
    vendors = [{
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "founded": "2013",  # already set — should NOT be overwritten
        "hq_address": "",   # empty — should be filled
        "funding_stage": "",
        "total_funding": "",
    }]
    upserts = []
    enrich_vendors_from_tracxn(vendors, upsert_fn=lambda k, v: upserts.append(v), skip_canary=True,
                                request_get=lambda *a, **k: _mock_response(SAMPLE_HTML))
    assert len(upserts) == 1
    assert "founded" not in upserts[0]  # already populated, must not overwrite
    assert "hq_address" in upserts[0] or "funding_stage" in upserts[0]


def test_enrich_vendors_aborts_on_canary_failure():
    result = enrich_vendors_from_tracxn(
        [{"vendor_name": "Gainsight", "website": "https://gainsight.com"}],
        request_get=lambda *a, **k: _mock_response("", 404),
        skip_canary=False,
    )
    assert result["skipped_canary"] is True
    assert result["attempted"] == 0
