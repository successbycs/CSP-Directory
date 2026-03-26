"""M61: Tests for new schema fields — youtube_channel_url, funding_stage, total_funding, use_case_details.

Requirements verified:
- VendorIntelligence has all four new fields with correct defaults
- _extract_youtube_channel_url detects channel, /c/, and @-handle URLs
- _extract_funding_stage detects pre-seed through public and bootstrapped
- _normalize_use_case_details normalises list-of-dicts and deduplicates labels
- extract_vendor_intelligence() populates youtube_channel_url and funding_stage from page text
- build_vendor_row() includes the new fields (tested by checking field presence on VendorIntelligence)
"""

from __future__ import annotations

import pytest

from services.extraction.vendor_intel import (
    VendorIntelligence,
    extract_vendor_intelligence,
    _extract_youtube_channel_url,
    _extract_funding_stage,
    _normalize_use_case_details,
)


# ---------------------------------------------------------------------------
# 1. _extract_youtube_channel_url
# ---------------------------------------------------------------------------


def test_extract_youtube_channel_url_detects_channel_path():
    text = "Subscribe at https://www.youtube.com/channel/UCabc123xyz for updates."
    url = _extract_youtube_channel_url(text)
    assert url == "https://www.youtube.com/channel/UCabc123xyz"


def test_extract_youtube_channel_url_detects_c_path():
    text = "Watch us at https://youtube.com/c/MyCompanyChannel"
    url = _extract_youtube_channel_url(text)
    assert "youtube.com/c/MyCompanyChannel" in url


def test_extract_youtube_channel_url_detects_at_handle():
    text = "Find us at https://youtube.com/@mycompany123"
    url = _extract_youtube_channel_url(text)
    assert "@mycompany123" in url


def test_extract_youtube_channel_url_returns_empty_when_no_youtube():
    text = "We post on Twitter and LinkedIn but not YouTube."
    url = _extract_youtube_channel_url(text)
    assert url == ""


def test_extract_youtube_channel_url_returns_empty_for_empty_text():
    assert _extract_youtube_channel_url("") == ""


def test_extract_youtube_channel_url_returns_first_match():
    text = (
        "Channel: https://youtube.com/channel/UCfirst "
        "and also https://youtube.com/channel/UCsecond"
    )
    url = _extract_youtube_channel_url(text)
    assert "UCfirst" in url


# ---------------------------------------------------------------------------
# 2. _extract_funding_stage
# ---------------------------------------------------------------------------


def test_extract_funding_stage_detects_series_a():
    assert _extract_funding_stage("We closed a Series A round.") == "Series A"


def test_extract_funding_stage_detects_series_b():
    assert _extract_funding_stage("backed by $20M Series B investors") == "Series B"


def test_extract_funding_stage_detects_series_c():
    assert _extract_funding_stage("Series C growth stage company") == "Series C"


def test_extract_funding_stage_detects_seed():
    assert _extract_funding_stage("seed funding stage startup") == "seed"


def test_extract_funding_stage_detects_pre_seed():
    assert _extract_funding_stage("we're a pre-seed startup") == "pre-seed"


def test_extract_funding_stage_detects_bootstrapped():
    assert _extract_funding_stage("bootstrapped and profitable") == "bootstrapped"


def test_extract_funding_stage_detects_public():
    assert _extract_funding_stage("publicly traded on NASDAQ") == "public"


def test_extract_funding_stage_returns_empty_when_no_match():
    assert _extract_funding_stage("We help customer success teams.") == ""


def test_extract_funding_stage_is_case_insensitive():
    assert _extract_funding_stage("SERIES A FUNDING") == "Series A"


# ---------------------------------------------------------------------------
# 3. _normalize_use_case_details
# ---------------------------------------------------------------------------


def test_normalize_use_case_details_returns_list_of_dicts():
    raw = [
        {"label": "Health Scoring", "url": "https://example.com/health", "summary": "Track health"},
    ]
    result = _normalize_use_case_details(raw)
    assert len(result) == 1
    assert result[0]["label"] == "Health Scoring"
    assert result[0]["url"] == "https://example.com/health"
    assert result[0]["summary"] == "Track health"


def test_normalize_use_case_details_deduplicates_by_label():
    raw = [
        {"label": "Health Scoring", "url": "https://example.com/1", "summary": "First"},
        {"label": "health scoring", "url": "https://example.com/2", "summary": "Dup"},
    ]
    result = _normalize_use_case_details(raw)
    assert len(result) == 1


def test_normalize_use_case_details_skips_empty_label():
    raw = [
        {"label": "", "url": "https://example.com", "summary": "No label"},
        {"label": "Renewal", "url": "", "summary": "Renewal use case"},
    ]
    result = _normalize_use_case_details(raw)
    assert len(result) == 1
    assert result[0]["label"] == "Renewal"


def test_normalize_use_case_details_truncates_summary():
    raw = [{"label": "Test", "url": "", "summary": "x" * 300}]
    result = _normalize_use_case_details(raw)
    assert len(result[0]["summary"]) <= 200


def test_normalize_use_case_details_returns_empty_for_empty_list():
    assert _normalize_use_case_details([]) == []


def test_normalize_use_case_details_returns_empty_for_string():
    assert _normalize_use_case_details("") == []


# ---------------------------------------------------------------------------
# 4. VendorIntelligence — new fields defaults and types
# ---------------------------------------------------------------------------


def test_vendor_intelligence_has_youtube_channel_url_field():
    vi = VendorIntelligence(vendor_name="Test", website="https://example.com")
    assert hasattr(vi, "youtube_channel_url")
    assert vi.youtube_channel_url == ""


def test_vendor_intelligence_has_funding_stage_field():
    vi = VendorIntelligence(vendor_name="Test", website="https://example.com")
    assert hasattr(vi, "funding_stage")
    assert vi.funding_stage == ""


def test_vendor_intelligence_has_total_funding_field():
    vi = VendorIntelligence(vendor_name="Test", website="https://example.com")
    assert hasattr(vi, "total_funding")
    assert vi.total_funding == ""


def test_vendor_intelligence_has_use_case_details_field():
    vi = VendorIntelligence(vendor_name="Test", website="https://example.com")
    assert hasattr(vi, "use_case_details")
    assert vi.use_case_details == []


def test_vendor_intelligence_accepts_youtube_channel_url():
    vi = VendorIntelligence(
        vendor_name="Test",
        website="https://example.com",
        youtube_channel_url="https://youtube.com/channel/UCtest",
    )
    assert "UCtest" in vi.youtube_channel_url


def test_vendor_intelligence_accepts_funding_stage():
    vi = VendorIntelligence(
        vendor_name="Test",
        website="https://example.com",
        funding_stage="Series A",
    )
    assert vi.funding_stage == "Series A"


def test_vendor_intelligence_accepts_use_case_details():
    vi = VendorIntelligence(
        vendor_name="Test",
        website="https://example.com",
        use_case_details=[{"label": "Health Scoring", "url": "", "summary": "Track health"}],
    )
    assert len(vi.use_case_details) == 1
    assert vi.use_case_details[0]["label"] == "Health Scoring"


def test_vendor_intelligence_validate_passes_with_new_fields():
    vi = VendorIntelligence(
        vendor_name="Test",
        website="https://example.com",
        youtube_channel_url="https://youtube.com/channel/UCtest",
        funding_stage="Series B",
        total_funding="$20M",
        use_case_details=[{"label": "Renewal", "url": "", "summary": ""}],
    )
    vi.validate()  # should not raise


# ---------------------------------------------------------------------------
# 5. extract_vendor_intelligence() — end-to-end wiring
# ---------------------------------------------------------------------------


def test_extract_vendor_intelligence_detects_youtube_from_homepage():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Watch our tutorials at https://youtube.com/channel/UCacme123.",
            "url": "https://acme.example.com",
        }
    }
    result = extract_vendor_intelligence(page_payload)
    assert "UCacme123" in result.youtube_channel_url


def test_extract_vendor_intelligence_detects_funding_stage():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "We closed our Series A and are growing fast.",
            "url": "https://acme.example.com",
        }
    }
    result = extract_vendor_intelligence(page_payload)
    assert result.funding_stage == "Series A"


def test_extract_vendor_intelligence_returns_empty_youtube_when_not_found():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "We use Salesforce and help customer success teams.",
            "url": "https://acme.example.com",
        }
    }
    result = extract_vendor_intelligence(page_payload)
    assert result.youtube_channel_url == ""
