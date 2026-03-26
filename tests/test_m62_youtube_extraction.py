"""M62: Tests for YouTube channel URL extraction — multi-page search + href detection.

Requirements verified:
- _extract_youtube_channel_url detects href= contexts (from rendered HTML)
- _extract_youtube_channel_url_from_pages searches homepage, about_page, contact_page in priority order
- extract_vendor_intelligence() uses multi-page search for youtube_channel_url
- channel/, /c/, and @-handle URL forms all detected
- Returns empty string when no YouTube URL found
"""

from __future__ import annotations

import pytest

from services.extraction.vendor_intel import (
    extract_vendor_intelligence,
    _extract_youtube_channel_url,
    _extract_youtube_channel_url_from_pages,
)


# ---------------------------------------------------------------------------
# 1. _extract_youtube_channel_url — href/link context detection (M62)
# ---------------------------------------------------------------------------


def test_extract_youtube_detects_href_attribute():
    """YouTube URL in href= attribute should be detected."""
    html = 'Follow us on <a href="https://youtube.com/channel/UCtest123">YouTube</a>'
    url = _extract_youtube_channel_url(html)
    assert "UCtest123" in url


def test_extract_youtube_detects_subscribe_link():
    """YouTube URL near 'subscribe' keyword should be detected."""
    text = 'subscribe https://youtube.com/@CompanyHandle for updates'
    url = _extract_youtube_channel_url(text)
    assert "CompanyHandle" in url


def test_extract_youtube_detects_channel_keyword():
    """YouTube URL near 'channel' keyword should be detected."""
    text = 'Our YouTube channel: https://youtube.com/c/MyBrand123'
    url = _extract_youtube_channel_url(text)
    assert "MyBrand123" in url


def test_extract_youtube_detects_bare_channel_url():
    """Bare YouTube channel URL without context should still be detected."""
    text = "Watch tutorials at https://www.youtube.com/channel/UCabc456"
    url = _extract_youtube_channel_url(text)
    assert "UCabc456" in url


def test_extract_youtube_detects_at_handle():
    """@handle-style YouTube URLs should be detected."""
    text = "Find us at https://youtube.com/@acmecorp"
    url = _extract_youtube_channel_url(text)
    assert "@acmecorp" in url


def test_extract_youtube_prefers_href_context_over_bare_url():
    """When both href and bare URL are present, href context is detected."""
    text = (
        'href="https://youtube.com/channel/UCprimary" and also '
        "bare https://youtube.com/channel/UCsecondary"
    )
    url = _extract_youtube_channel_url(text)
    # href context is preferred
    assert "UCprimary" in url


def test_extract_youtube_returns_empty_for_regular_youtube_watch_url():
    """A youtube.com/watch?v= URL is not a channel and should not be returned."""
    text = "Watch this video: https://youtube.com/watch?v=abc123"
    url = _extract_youtube_channel_url(text)
    assert url == ""


def test_extract_youtube_returns_empty_when_no_youtube():
    """Non-YouTube social links should not match."""
    text = "Follow us on Twitter at https://twitter.com/company and LinkedIn."
    url = _extract_youtube_channel_url(text)
    assert url == ""


# ---------------------------------------------------------------------------
# 2. _extract_youtube_channel_url_from_pages — multi-page priority search
# ---------------------------------------------------------------------------


def test_from_pages_finds_url_on_homepage():
    page_payloads = {
        "homepage": {"text": "Watch us at https://youtube.com/channel/UChomepage", "url": "https://example.com"},
    }
    url = _extract_youtube_channel_url_from_pages(page_payloads)
    assert "UChomepage" in url


def test_from_pages_finds_url_on_about_page_when_not_on_homepage():
    page_payloads = {
        "homepage": {"text": "No YouTube here.", "url": "https://example.com"},
        "about_page": {"text": "Subscribe: https://youtube.com/@aboutchannel", "url": "https://example.com/about"},
    }
    url = _extract_youtube_channel_url_from_pages(page_payloads)
    assert "aboutchannel" in url


def test_from_pages_finds_url_on_contact_page():
    page_payloads = {
        "homepage": {"text": "No YouTube here.", "url": "https://example.com"},
        "about_page": {"text": "No YouTube here either.", "url": "https://example.com/about"},
        "contact_page": {"text": "Find us at https://youtube.com/c/ContactChannel", "url": "https://example.com/contact"},
    }
    url = _extract_youtube_channel_url_from_pages(page_payloads)
    assert "ContactChannel" in url


def test_from_pages_prefers_homepage_over_about():
    """Homepage is searched first — if found there, about_page result is not used."""
    page_payloads = {
        "homepage": {"text": "https://youtube.com/channel/UCfirst", "url": "https://example.com"},
        "about_page": {"text": "https://youtube.com/channel/UCsecond", "url": "https://example.com/about"},
    }
    url = _extract_youtube_channel_url_from_pages(page_payloads)
    assert "UCfirst" in url


def test_from_pages_returns_empty_when_no_youtube_anywhere():
    page_payloads = {
        "homepage": {"text": "We help SaaS companies.", "url": "https://example.com"},
        "about_page": {"text": "About us.", "url": "https://example.com/about"},
    }
    url = _extract_youtube_channel_url_from_pages(page_payloads)
    assert url == ""


def test_from_pages_handles_empty_page_payloads():
    assert _extract_youtube_channel_url_from_pages({}) == ""


# ---------------------------------------------------------------------------
# 3. extract_vendor_intelligence() — end-to-end multi-page YouTube extraction
# ---------------------------------------------------------------------------


def test_extract_vendor_intelligence_finds_youtube_on_about_page():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps SaaS companies.",
            "url": "https://acme.example.com",
        },
        "about_page": {
            "text": 'Follow us on YouTube: href="https://youtube.com/channel/UCacme456"',
            "url": "https://acme.example.com/about",
        },
    }
    result = extract_vendor_intelligence(page_payload)
    assert "UCacme456" in result.youtube_channel_url


def test_extract_vendor_intelligence_finds_youtube_on_homepage():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Watch our channel at https://youtube.com/@acmechannel123 for tutorials.",
            "url": "https://acme.example.com",
        },
    }
    result = extract_vendor_intelligence(page_payload)
    assert "acmechannel123" in result.youtube_channel_url


def test_extract_vendor_intelligence_youtube_empty_when_not_present():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "We help customer success teams adopt faster.",
            "url": "https://acme.example.com",
        },
    }
    result = extract_vendor_intelligence(page_payload)
    assert result.youtube_channel_url == ""
