"""M56: Tests confirming case_study_signals stores detection keywords and
case_study_details (not case_studies) appears in the public export.

Requirements verified:
- case_study_signals stores keyword detection strings (e.g., "case study", "customer story")
- case_studies on VendorIntelligence is always empty from rule-based extraction
- The public export (build_directory_dataset / _normalize_vendor_row) contains
  case_study_details (list of dicts with source_url) and NOT a flat case_studies field
  holding keyword strings
- _list_value is not applied to case_study_details (it stays as list-of-dicts)
"""

from __future__ import annotations

import pytest

from services.export import directory_dataset
from services.extraction.vendor_intel import (
    VendorIntelligence,
    extract_vendor_intelligence,
)


# ---------------------------------------------------------------------------
# 1. Detection keywords land in case_study_signals, NOT in case_studies
# ---------------------------------------------------------------------------


def test_rule_based_extraction_puts_keywords_in_case_study_signals_not_case_studies():
    """Keywords like 'case study' must appear in case_study_signals, not case_studies."""
    page_payload = {
        "homepage": {
            "vendor_name": "AcmeCo",
            "website": "https://acme.example.com",
            "text": "We help SaaS teams. Read our case studies and customer stories.",
            "url": "https://acme.example.com",
        },
        "case_studies_page": {
            "text": "Check out our case studies. Customers trust us.",
            "url": "https://acme.example.com/case-studies",
        },
    }

    result = extract_vendor_intelligence(page_payload)

    assert "case study" in result.case_study_signals, (
        "Expected 'case study' keyword to be in case_study_signals"
    )
    assert result.case_studies == [], (
        "case_studies must be empty from rule-based extraction; keywords go in case_study_signals"
    )


def test_rule_based_extraction_customer_story_keyword_in_case_study_signals():
    """'customer story' keyword must land in case_study_signals, not case_studies."""
    page_payload = {
        "homepage": {
            "vendor_name": "BetaCo",
            "website": "https://beta.example.com",
            "text": "Read our customer stories and learn how we deliver value.",
            "url": "https://beta.example.com",
        },
    }

    result = extract_vendor_intelligence(page_payload)

    assert "customer story" in result.case_study_signals
    assert result.case_studies == []


def test_rule_based_extraction_no_case_study_signals_when_no_matching_text():
    """When no case-study keywords are present, case_study_signals is empty."""
    page_payload = {
        "homepage": {
            "vendor_name": "GammaCo",
            "website": "https://gamma.example.com",
            "text": "We provide analytics and reporting for SaaS companies.",
            "url": "https://gamma.example.com",
        },
    }

    result = extract_vendor_intelligence(page_payload)

    assert result.case_studies == []
    assert result.case_study_signals == []


# ---------------------------------------------------------------------------
# 2. Public export contains case_study_details (list-of-dicts), not case_studies keywords
# ---------------------------------------------------------------------------


def test_normalize_vendor_row_exports_case_study_details_not_keyword_strings():
    """_normalize_vendor_row must produce case_study_details (list of dicts), not case_studies."""
    row = {
        "name": "TestVendor",
        "website": "https://tv.example.com",
        "case_study_details": [
            {
                "client": "Acme",
                "title": "Acme case study",
                "use_case": "renewal management",
                "value_realized": "reduced churn by 20%",
                "source_url": "https://tv.example.com/customers/acme/",
            }
        ],
        "case_studies": ["case study", "customer story"],  # old keyword strings — must NOT appear
    }

    normalized = directory_dataset._normalize_vendor_row(row)

    assert "case_study_details" in normalized, "Public export must include case_study_details"
    assert "case_studies" not in normalized, "Public export must NOT include a case_studies key"
    assert len(normalized["case_study_details"]) == 1
    assert normalized["case_study_details"][0]["client"] == "Acme"
    assert normalized["case_study_details"][0]["source_url"].rstrip("/") == "https://tv.example.com/customers/acme"


def test_normalize_vendor_row_case_study_details_empty_when_not_present():
    """When case_study_details is absent from the row, the export key is an empty list."""
    row = {
        "name": "EmptyVendor",
        "website": "https://empty.example.com",
    }

    normalized = directory_dataset._normalize_vendor_row(row)

    assert "case_study_details" in normalized
    assert normalized["case_study_details"] == []
    assert "case_studies" not in normalized


def test_directory_dataset_fields_contains_case_study_details_not_case_studies():
    """DIRECTORY_DATASET_FIELDS tuple must contain case_study_details and not case_studies."""
    assert "case_study_details" in directory_dataset.DIRECTORY_DATASET_FIELDS, (
        "DIRECTORY_DATASET_FIELDS must include case_study_details"
    )
    assert "case_studies" not in directory_dataset.DIRECTORY_DATASET_FIELDS, (
        "DIRECTORY_DATASET_FIELDS must NOT contain case_studies (keyword strings)"
    )


# ---------------------------------------------------------------------------
# 3. Profile-to-row conversion uses case_study_details, not case_studies
# ---------------------------------------------------------------------------


def test_profile_to_vendor_row_uses_case_study_details():
    """_profile_to_vendor_row must map profile.case_study_details, not profile.case_studies."""
    profile = VendorIntelligence(
        vendor_name="ProfileVendor",
        website="https://pv.example.com",
        case_study_details=[
            {
                "client": "Beta Inc",
                "title": "Beta Inc case study",
                "use_case": "onboarding",
                "value_realized": "cut time-to-value by 30%",
                "source_url": "https://pv.example.com/customers/beta/",
            }
        ],
        case_studies=["case study"],  # keyword strings — must NOT reach the export
        include_in_directory=True,
        directory_fit="high",
        directory_category="cs_core",
    )

    row = directory_dataset._profile_to_vendor_row(profile)

    assert "case_study_details" in row
    assert "case_studies" not in row
    assert len(row["case_study_details"]) == 1
    assert row["case_study_details"][0]["client"] == "Beta Inc"


# ---------------------------------------------------------------------------
# 4. End-to-end: build_directory_dataset export has no keyword strings in case_study_details
# ---------------------------------------------------------------------------


def test_build_directory_dataset_case_study_details_contains_only_url_dicts(monkeypatch):
    """End-to-end: exported dataset case_study_details must be list of dicts with source_url."""
    monkeypatch.setattr(directory_dataset.supabase_client, "is_configured", lambda: False)

    profile = VendorIntelligence(
        vendor_name="E2EVendor",
        website="https://e2e.example.com",
        case_study_details=[
            {
                "client": "Gamma Corp",
                "title": "Gamma Corp success story",
                "use_case": "churn prevention",
                "value_realized": "reduced churn by 15%",
                "source_url": "https://e2e.example.com/customers/gamma/",
            }
        ],
        case_studies=["case study", "customer story"],  # keywords must NOT appear in export
        include_in_directory=True,
        directory_fit="high",
        directory_category="cs_core",
    )

    dataset = directory_dataset.build_directory_dataset(
        fallback_profiles=[profile]
    )

    assert len(dataset) == 1
    vendor = dataset[0]

    assert "case_study_details" in vendor
    assert "case_studies" not in vendor

    # All items must be dicts (not keyword strings)
    for item in vendor["case_study_details"]:
        assert isinstance(item, dict), f"Expected dict, got {type(item)}: {item!r}"
        assert "source_url" in item, "Each case_study_details item must have a source_url"

    # The keyword strings must not appear anywhere in the export
    import json
    serialized = json.dumps(vendor)
    assert "customer story" not in serialized or vendor.get("case_studies") is None
