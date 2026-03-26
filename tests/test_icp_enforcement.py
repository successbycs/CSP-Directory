"""M48: ICP enforcement — vendors with empty ICP must not appear in the directory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.pipeline_health_check import check_empty_icp_violations
from services.extraction.vendor_intel import VendorIntelligence
from services.pipeline.orchestrator import _drop_reason


# ---------------------------------------------------------------------------
# Health check: check_empty_icp_violations
# ---------------------------------------------------------------------------


def test_empty_icp_health_check_flags_included_vendor_with_no_icp():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "icp": []}]
    assert check_empty_icp_violations(rows) == ["https://vendor.com"]


def test_empty_icp_health_check_flags_included_vendor_with_null_icp():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "icp": None}]
    assert check_empty_icp_violations(rows) == ["https://vendor.com"]


def test_empty_icp_health_check_passes_included_vendor_with_icp():
    rows = [{"website": "https://vendor.com", "include_in_directory": True, "icp": ["SMB"]}]
    assert check_empty_icp_violations(rows) == []


def test_empty_icp_health_check_ignores_excluded_vendor():
    rows = [{"website": "https://vendor.com", "include_in_directory": False, "icp": []}]
    assert check_empty_icp_violations(rows) == []


def test_empty_icp_health_check_ignores_vendor_not_reviewed():
    rows = [{"website": "https://vendor.com", "include_in_directory": None, "icp": []}]
    assert check_empty_icp_violations(rows) == []


# ---------------------------------------------------------------------------
# Drop reason: empty ICP gates directory inclusion
# ---------------------------------------------------------------------------


def _make_profile(**kwargs) -> VendorIntelligence:
    defaults = dict(
        vendor_name="Test Vendor",
        website="https://vendor.com",
        confidence="high",
        directory_fit="strong",
        directory_category="customer_success",
        include_in_directory=True,
        icp=["SMB"],
        lifecycle_stages=["onboarding"],
    )
    defaults.update(kwargs)
    return VendorIntelligence(**defaults)


def test_drop_reason_empty_icp_returns_empty_icp():
    profile = _make_profile(icp=[])
    assert _drop_reason(profile, None) == "empty_icp"


def test_drop_reason_populated_icp_does_not_drop():
    profile = _make_profile(icp=["Enterprise"])
    assert _drop_reason(profile, None) == ""


def test_drop_reason_llm_non_cs_relevant_takes_priority_over_empty_icp():
    profile = _make_profile(icp=[])
    llm_result = MagicMock()
    llm_result.is_cs_relevant = False
    assert _drop_reason(profile, llm_result) == "llm_marked_non_cs_relevant"


def test_drop_reason_low_confidence_takes_priority_over_empty_icp():
    profile = _make_profile(icp=[], confidence="low")
    assert _drop_reason(profile, None) == "low_confidence"


# ---------------------------------------------------------------------------
# Fetch gating: skip_expensive_fetch bypasses Playwright/Apify
# ---------------------------------------------------------------------------


def test_fetch_homepage_skips_expensive_fetch_when_flagged():
    """When skip_expensive_fetch=True, blocked pages do not trigger Playwright/Apify."""
    from services.enrichment.vendor_fetcher import fetch_vendor_homepage

    vendor = {"vendor_name": "Test", "website": "https://vendor.com", "skip_expensive_fetch": True}

    blocked_response = MagicMock()
    blocked_response.status_code = 403
    blocked_response.text = "403 forbidden"

    with patch("services.enrichment.vendor_fetcher.requests.get", return_value=blocked_response), \
         patch("services.enrichment.vendor_fetcher.fetch_page_with_fallback") as mock_fallback:
        result = fetch_vendor_homepage(vendor)

    mock_fallback.assert_not_called()
    assert result["fetch_backend"] == "requests"


def test_fetch_homepage_uses_expensive_fetch_when_not_flagged():
    """Without skip flag, blocked pages fall through to Playwright/Apify."""
    from services.enrichment.vendor_fetcher import fetch_vendor_homepage

    vendor = {"vendor_name": "Test", "website": "https://vendor.com"}

    blocked_response = MagicMock()
    blocked_response.status_code = 403
    blocked_response.text = "403 forbidden"

    fallback_payload = {
        "status_code": 200,
        "html": "<html><body>content</body></html>",
        "text": "Some vendor content",
        "fetch_backend": "playwright",
    }

    with patch("services.enrichment.vendor_fetcher.requests.get", return_value=blocked_response), \
         patch("services.enrichment.vendor_fetcher.fetch_page_with_fallback", return_value=fallback_payload):
        result = fetch_vendor_homepage(vendor)

    assert result["fetch_backend"] == "playwright"
    assert result["text"] == "Some vendor content"
