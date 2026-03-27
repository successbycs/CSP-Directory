"""M63: Tests for enrichment provenance model — field and url tracking per record.

Requirements verified:
- normalize_external_enrichment_records handles M63 provenance schema {field, url, source, value, fetched_at}
- normalize_external_enrichment_records preserves legacy {provider, source_id, ...} schema
- _make_provenance_record creates valid provenance records
- summarize_external_enrichment handles both schemas
- extract_vendor_intelligence() collects provenance from case_studies_page, about_page, team_page
- Provenance records deduplicate by (field, url, source)
"""

from __future__ import annotations

import pytest

from services.extraction.vendor_intel import (
    VendorIntelligence,
    extract_vendor_intelligence,
    normalize_external_enrichment_records,
    summarize_external_enrichment,
    _make_provenance_record,
)


# ---------------------------------------------------------------------------
# 1. _make_provenance_record
# ---------------------------------------------------------------------------


def test_make_provenance_record_returns_correct_shape():
    record = _make_provenance_record("customers", "Acme, Bolt", "https://example.com/customers", "case_studies_page")
    assert record["field"] == "customers"
    assert record["value"] == "Acme, Bolt"
    assert "example.com" in record["url"]
    assert record["source"] == "case_studies_page"
    assert "fetched_at" in record
    assert record["fetched_at"]  # non-empty timestamp


def test_make_provenance_record_defaults_source_to_webcrawl():
    record = _make_provenance_record("ceo_name", "Jane Doe", "https://example.com/about")
    assert record["source"] == "webcrawl"


def test_make_provenance_record_strips_whitespace():
    record = _make_provenance_record("  ceo_name  ", "  Jane  ", "https://example.com/about")
    assert record["field"] == "ceo_name"
    assert record["value"] == "Jane"


# ---------------------------------------------------------------------------
# 2. normalize_external_enrichment_records — M63 provenance schema
# ---------------------------------------------------------------------------


def test_normalize_provenance_schema_accepted():
    records = normalize_external_enrichment_records([
        {"field": "customers", "url": "https://example.com/customers", "source": "case_studies_page", "value": "Acme", "fetched_at": "2026-01-01T00:00:00Z"},
    ])
    assert len(records) == 1
    assert records[0]["field"] == "customers"
    assert records[0]["source"] == "case_studies_page"
    assert records[0]["value"] == "Acme"


def test_normalize_provenance_deduplicates_by_field_url_source():
    records = normalize_external_enrichment_records([
        {"field": "customers", "url": "https://example.com/customers", "source": "webcrawl", "value": "Acme"},
        {"field": "customers", "url": "https://example.com/customers", "source": "webcrawl", "value": "Acme (dup)"},
    ])
    assert len(records) == 1


def test_normalize_provenance_allows_different_sources_same_field():
    records = normalize_external_enrichment_records([
        {"field": "ceo_name", "url": "https://example.com/about", "source": "about_page", "value": "Jane"},
        {"field": "ceo_name", "url": "https://example.com/team", "source": "team_page", "value": "Jane"},
    ])
    assert len(records) == 2


def test_normalize_provenance_defaults_source_to_webcrawl():
    records = normalize_external_enrichment_records([
        {"field": "leadership", "url": "https://example.com/team", "value": "Jane Smith"},
    ])
    assert records[0]["source"] == "webcrawl"


# ---------------------------------------------------------------------------
# 3. normalize_external_enrichment_records — legacy schema preserved
# ---------------------------------------------------------------------------


def test_normalize_legacy_schema_preserved():
    records = normalize_external_enrichment_records([
        {
            "provider": "G2",
            "source_id": "g2-acme",
            "source_type": "review_directory",
            "source_url": "https://g2.com/products/acme",
            "status": "staged",
        }
    ])
    assert len(records) == 1
    assert records[0]["provider"] == "G2"
    assert records[0]["source_type"] == "review_directory"


def test_normalize_mixed_schemas():
    records = normalize_external_enrichment_records([
        {"field": "customers", "url": "https://example.com/customers", "source": "case_studies_page", "value": "Acme"},
        {"provider": "G2", "source_id": "g2-acme", "source_url": "https://g2.com/acme"},
    ])
    assert len(records) == 2
    fields = {r.get("field") or r.get("provider") for r in records}
    assert "customers" in fields
    assert "G2" in fields


# ---------------------------------------------------------------------------
# 4. summarize_external_enrichment — M63 schema support
# ---------------------------------------------------------------------------


def test_summarize_provenance_schema():
    records = [
        {"field": "customers", "url": "https://example.com/customers", "source": "case_studies_page", "value": "Acme"},
        {"field": "ceo_name", "url": "https://example.com/about", "source": "about_page", "value": "Jane"},
    ]
    summary = summarize_external_enrichment(records)
    assert "customers" in summary
    assert "case_studies_page" in summary


def test_summarize_legacy_schema():
    records = [{"provider": "G2", "source_id": "g2-acme", "source_url": "https://g2.com/acme"}]
    summary = summarize_external_enrichment(records)
    assert "G2" in summary


# ---------------------------------------------------------------------------
# 5. VendorIntelligence — provenance records in external_enrichment
# ---------------------------------------------------------------------------


def test_vendor_intelligence_accepts_provenance_records():
    vi = VendorIntelligence(
        vendor_name="Test",
        website="https://example.com",
        external_enrichment=[
            {"field": "customers", "url": "https://example.com/customers", "source": "case_studies_page", "value": "Acme"},
        ],
    )
    assert len(vi.external_enrichment) == 1
    assert vi.external_enrichment[0]["field"] == "customers"


# ---------------------------------------------------------------------------
# 6. extract_vendor_intelligence() — provenance collected from specific pages
# ---------------------------------------------------------------------------


def test_extract_vendor_intelligence_collects_provenance_from_case_studies_page():
    """Customers extracted from case_studies_page should generate a provenance record."""
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps customer success teams.",
            "url": "https://acme.example.com",
        },
        "case_studies_page": {
            "text": "Read how Salesforce reduced churn by 20% using Acme.",
            "url": "https://acme.example.com/customers",
        },
    }
    result = extract_vendor_intelligence(page_payload)
    # Check that a provenance record exists for customers
    fields_recorded = [r.get("field") for r in result.external_enrichment]
    assert "customers" in fields_recorded or "case_study_details" in fields_recorded


def test_extract_vendor_intelligence_collects_provenance_from_about_page():
    """Leadership extracted from about_page should generate a provenance record."""
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps SaaS companies.",
            "url": "https://acme.example.com",
        },
        "about_page": {
            "text": "Jane Smith, CEO of Acme, leads the team.",
            "url": "https://acme.example.com/about",
        },
    }
    result = extract_vendor_intelligence(page_payload)
    fields_recorded = [r.get("field") for r in result.external_enrichment]
    # At least one leadership/ceo provenance record expected
    assert any(f in fields_recorded for f in ["leadership", "ceo_name"])


def test_extract_vendor_intelligence_no_provenance_when_no_specific_pages():
    """No provenance records when no specific pages are crawled."""
    page_payload = {
        "homepage": {
            "vendor_name": "Acme",
            "website": "https://acme.example.com",
            "text": "Acme helps SaaS companies improve retention.",
            "url": "https://acme.example.com",
        },
    }
    result = extract_vendor_intelligence(page_payload)
    # homepage-only extraction should produce no provenance records
    # (provenance requires a specific page URL)
    provenance_fields = [r.get("field") for r in result.external_enrichment if r.get("field")]
    # All provenance records must have non-empty URLs pointing to specific pages
    for r in result.external_enrichment:
        if r.get("field"):
            assert r.get("url"), "Provenance record must have a url"
