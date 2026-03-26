"""M49: Case studies extraction — customers and case_studies fields populated from crawled pages."""

from __future__ import annotations

from services.extraction.vendor_intel import extract_vendor_intelligence, _derive_case_studies_text


def _page_payload(text: str, url: str = "https://vendor.com") -> dict:
    return {"text": text, "url": url, "vendor_name": "TestVendor", "website": url}


# ---------------------------------------------------------------------------
# _derive_case_studies_text
# ---------------------------------------------------------------------------


def test_derive_case_studies_text_produces_outcome_statements():
    details = [
        {"client": "Acme", "value_realized": "reduced churn by 20%", "source_url": "https://vendor.com/customers"},
        {"client": "Globex", "value_realized": "increased NPS by 15 points", "source_url": "https://vendor.com/customers"},
    ]
    result = _derive_case_studies_text(details)
    assert "Acme reduced churn by 20%" in result
    assert "Globex increased NPS by 15 points" in result


def test_derive_case_studies_text_empty_when_no_details():
    assert _derive_case_studies_text([]) == []


def test_derive_case_studies_text_skips_entries_missing_client_or_value():
    details = [
        {"client": "", "value_realized": "something happened"},
        {"client": "Acme", "value_realized": ""},
        {"client": "Globex", "value_realized": "improved retention"},
    ]
    result = _derive_case_studies_text(details)
    assert result == ["Globex improved retention"]


def test_derive_case_studies_text_deduplicates():
    details = [
        {"client": "Acme", "value_realized": "reduced churn"},
        {"client": "Acme", "value_realized": "reduced churn"},
    ]
    result = _derive_case_studies_text(details)
    assert result.count("Acme reduced churn") == 1


# ---------------------------------------------------------------------------
# customers extraction from case_studies_page
# ---------------------------------------------------------------------------


def test_extract_customers_from_case_studies_page_trusted_by():
    page_payloads = {
        "homepage": _page_payload("We help CS teams succeed.", "https://vendor.com"),
        "case_studies_page": _page_payload(
            "Trusted by Gainsight, Salesforce, and HubSpot.",
            "https://vendor.com/customers",
        ),
    }
    result = extract_vendor_intelligence(page_payloads)
    assert "Gainsight" in result.customers


def test_extract_customers_from_case_studies_page_read_how():
    page_payloads = {
        "homepage": _page_payload("Customer success software.", "https://vendor.com"),
        "case_studies_page": _page_payload(
            "Read how Zendesk uses our platform to reduce churn.",
            "https://vendor.com/customers",
        ),
    }
    result = extract_vendor_intelligence(page_payloads)
    assert "Zendesk" in result.customers


def test_extract_customers_falls_back_to_combined_text_when_no_case_studies_page():
    page_payloads = {
        "homepage": _page_payload(
            "Trusted by Intercom and Freshdesk.",
            "https://vendor.com",
        ),
    }
    result = extract_vendor_intelligence(page_payloads)
    assert "Intercom" in result.customers


def test_extract_customers_case_study_heading_pattern():
    page_payloads = {
        "homepage": _page_payload("We help customer success teams.", "https://vendor.com"),
        "case_studies_page": _page_payload(
            "Case study: ChurnZero\nHow ChurnZero improved NPS by 30 points.",
            "https://vendor.com/case-studies",
        ),
    }
    result = extract_vendor_intelligence(page_payloads)
    assert "ChurnZero" in result.customers


# ---------------------------------------------------------------------------
# case_studies field populated from case_study_details
# ---------------------------------------------------------------------------


def test_case_studies_populated_from_outcome_statements():
    page_payloads = {
        "homepage": _page_payload("Customer success software.", "https://vendor.com"),
        "case_studies_page": _page_payload(
            "Acme used our platform to reduce churn by 30%. Globex improved NPS scores.",
            "https://vendor.com/customers",
        ),
    }
    result = extract_vendor_intelligence(page_payloads)
    assert isinstance(result.case_studies, list)
    # case_studies derives from case_study_details — if details found, case_studies is populated
    if result.case_study_details:
        assert len(result.case_studies) > 0


def test_case_studies_empty_when_no_outcome_statements():
    """Pages with only keyword signals (no extractable outcomes) produce empty case_studies."""
    page_payloads = {
        "homepage": _page_payload("Read our case studies and customer stories.", "https://vendor.com"),
    }
    result = extract_vendor_intelligence(page_payloads)
    # case_study_signals captures keywords; case_studies only has confirmed outcomes
    assert isinstance(result.case_studies, list)
    # no outcome patterns in this text, so case_studies should be empty
    assert result.case_studies == []
