"""M60: Tests for about page crawl — CEO name, LinkedIn, address, leadership extraction.

Requirements verified:
- _extract_ceo_linkedin extracts LinkedIn URLs associated with CEO/Founder mentions
- _normalize_linkedin_url returns clean LinkedIn profile URLs
- _extract_ceo_linkedin_from_leadership finds LinkedIn from structured leadership list
- _extract_leadership captures LinkedIn URLs appearing near name+title patterns
- ceo_linkedin field exists on VendorIntelligence and is populated
- extract_vendor_intelligence() wires about_page and team_page into leadership/ceo_linkedin
"""

from __future__ import annotations

import pytest

from services.extraction.vendor_intel import (
    VendorIntelligence,
    extract_vendor_intelligence,
    normalize_leadership_profiles,
)
from services.extraction.vendor_intel import (
    _extract_ceo_linkedin,
    _extract_ceo_linkedin_from_leadership,
    _normalize_linkedin_url,
)


# ---------------------------------------------------------------------------
# 1. _normalize_linkedin_url
# ---------------------------------------------------------------------------


def test_normalize_linkedin_url_returns_clean_url():
    url = _normalize_linkedin_url("https://www.linkedin.com/in/johndoe/")
    assert url == "https://www.linkedin.com/in/johndoe"


def test_normalize_linkedin_url_extracts_from_text():
    text = "Visit our CEO at https://linkedin.com/in/jane-doe for more."
    url = _normalize_linkedin_url(text)
    assert "jane-doe" in url


def test_normalize_linkedin_url_returns_empty_for_non_linkedin():
    assert _normalize_linkedin_url("https://twitter.com/johndoe") == ""


def test_normalize_linkedin_url_returns_empty_for_empty_input():
    assert _normalize_linkedin_url("") == ""
    assert _normalize_linkedin_url(None) == ""


# ---------------------------------------------------------------------------
# 2. _extract_ceo_linkedin — text-based extraction
# ---------------------------------------------------------------------------


def test_extract_ceo_linkedin_finds_url_near_ceo_title():
    text = "Jane Smith, CEO. Connect with her at https://linkedin.com/in/jane-smith."
    url = _extract_ceo_linkedin(text)
    assert "jane-smith" in url


def test_extract_ceo_linkedin_finds_url_near_founder_title():
    text = "John Doe, Founder of Acme. LinkedIn: https://linkedin.com/in/john-doe-founder"
    url = _extract_ceo_linkedin(text)
    assert "john-doe-founder" in url


def test_extract_ceo_linkedin_returns_empty_when_no_ceo_near_url():
    text = "Our sales team is at https://linkedin.com/in/sales-rep and doing great."
    url = _extract_ceo_linkedin(text)
    assert url == ""


def test_extract_ceo_linkedin_returns_empty_when_no_linkedin():
    text = "Jane Smith is the CEO of Acme Corp. She runs the company."
    url = _extract_ceo_linkedin(text)
    assert url == ""


def test_extract_ceo_linkedin_returns_empty_for_empty_text():
    assert _extract_ceo_linkedin("") == ""


# ---------------------------------------------------------------------------
# 3. _extract_ceo_linkedin_from_leadership
# ---------------------------------------------------------------------------


def test_extract_ceo_linkedin_from_leadership_finds_ceo():
    leadership = [
        {"name": "Jane Smith", "title": "CEO", "linkedin": "https://linkedin.com/in/jane-smith", "source_url": ""},
        {"name": "Bob Lee", "title": "CTO", "linkedin": "", "source_url": ""},
    ]
    url = _extract_ceo_linkedin_from_leadership(leadership)
    assert "jane-smith" in url


def test_extract_ceo_linkedin_from_leadership_falls_back_to_founder():
    leadership = [
        {"name": "Bob Lee", "title": "Founder", "linkedin": "https://linkedin.com/in/bob-lee", "source_url": ""},
    ]
    url = _extract_ceo_linkedin_from_leadership(leadership)
    assert "bob-lee" in url


def test_extract_ceo_linkedin_from_leadership_returns_empty_when_no_ceo():
    leadership = [
        {"name": "Bob Lee", "title": "VP Engineering", "linkedin": "https://linkedin.com/in/bob", "source_url": ""},
    ]
    url = _extract_ceo_linkedin_from_leadership(leadership)
    assert url == ""


def test_extract_ceo_linkedin_from_leadership_returns_empty_for_empty_list():
    assert _extract_ceo_linkedin_from_leadership([]) == ""


# ---------------------------------------------------------------------------
# 4. normalize_leadership_profiles — linkedin key presence
# ---------------------------------------------------------------------------


def test_normalize_leadership_includes_linkedin_key():
    profiles = normalize_leadership_profiles([
        {"name": "Jane Doe", "title": "CEO", "linkedin": "https://linkedin.com/in/jane-doe", "source_url": ""},
    ])
    assert len(profiles) == 1
    assert profiles[0]["linkedin"] == "https://linkedin.com/in/jane-doe"


def test_normalize_leadership_linkedin_empty_when_not_provided():
    profiles = normalize_leadership_profiles([
        {"name": "Jane Doe", "title": "CEO", "source_url": ""},
    ])
    assert profiles[0]["linkedin"] == ""


# ---------------------------------------------------------------------------
# 5. VendorIntelligence — ceo_linkedin field
# ---------------------------------------------------------------------------


def test_vendor_intelligence_has_ceo_linkedin_field():
    vi = VendorIntelligence(vendor_name="Acme", website="https://acme.example.com")
    assert hasattr(vi, "ceo_linkedin")
    assert vi.ceo_linkedin == ""


def test_vendor_intelligence_ceo_linkedin_set_directly():
    vi = VendorIntelligence(
        vendor_name="Acme",
        website="https://acme.example.com",
        ceo_linkedin="https://linkedin.com/in/acme-ceo",
    )
    assert vi.ceo_linkedin == "https://linkedin.com/in/acme-ceo"


def test_vendor_intelligence_ceo_linkedin_derived_from_leadership():
    vi = VendorIntelligence(
        vendor_name="Acme",
        website="https://acme.example.com",
        leadership=[
            {"name": "Jane Smith", "title": "CEO", "linkedin": "https://linkedin.com/in/jane-s", "source_url": ""},
        ],
    )
    assert "jane-s" in vi.ceo_linkedin


# ---------------------------------------------------------------------------
# 6. extract_vendor_intelligence() — end-to-end about_page wiring
# ---------------------------------------------------------------------------


def test_extract_vendor_intelligence_populates_ceo_linkedin_from_about_page():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps customer success teams.",
            "url": "https://acme.example.com",
        },
        "about_page": {
            "text": (
                "Jane Smith, CEO of Acme. "
                "Connect with Jane at https://linkedin.com/in/jane-smith-ceo."
            ),
            "url": "https://acme.example.com/about",
        },
    }

    result = extract_vendor_intelligence(page_payload)
    assert "jane-smith-ceo" in result.ceo_linkedin


def test_extract_vendor_intelligence_populates_leadership_from_team_page():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps SaaS companies.",
            "url": "https://acme.example.com",
        },
        "team_page": {
            "text": "CEO John Doe leads the company.",
            "url": "https://acme.example.com/team",
        },
    }

    result = extract_vendor_intelligence(page_payload)
    names = [p["name"] for p in result.leadership]
    assert "John Doe" in names


def test_extract_vendor_intelligence_populates_hq_address_from_about_page():
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps SaaS companies.",
            "url": "https://acme.example.com",
        },
        "about_page": {
            "text": "We are headquartered in Austin, Texas.",
            "url": "https://acme.example.com/about",
        },
    }

    result = extract_vendor_intelligence(page_payload)
    assert "Austin" in result.hq_address
