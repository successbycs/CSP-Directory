"""Tests for lightweight admin actions."""

from services.admin import admin_actions
from services.extraction.vendor_intel import VendorIntelligence


def test_include_vendor_updates_directory_flag():
    calls = []

    result = admin_actions.include_vendor(
        "gainsight",
        update_vendor_admin_fields_fn=lambda vendor, **kwargs: calls.append((vendor, kwargs)) or {"name": "Gainsight"},
    )

    assert result["ok"] is True
    assert result["action"] == "include"
    assert calls == [("gainsight", {"include_in_directory": True})]


def test_exclude_vendor_updates_directory_flag():
    calls = []

    result = admin_actions.exclude_vendor(
        "gainsight",
        update_vendor_admin_fields_fn=lambda vendor, **kwargs: calls.append((vendor, kwargs)) or {"name": "Gainsight"},
    )

    assert result["ok"] is True
    assert result["action"] == "exclude"
    assert calls == [("gainsight", {"include_in_directory": False})]


def test_rerun_vendor_enrichment_rebuilds_and_upserts_profile():
    upserts = []
    result = admin_actions.rerun_vendor_enrichment(
        "https://example.com",
        find_vendor_by_lookup_fn=lambda lookup: {
            "name": "ExampleCorp",
            "website": "https://example.com",
            "source": "google_search",
            "raw_description": "Customer success platform",
        },
        fetch_vendor_homepage_fn=lambda vendor: {"vendor_name": "ExampleCorp", "website": "https://example.com", "text": "Homepage"},
        explore_vendor_site_fn=lambda homepage: {"homepage": homepage, "extra_pages": []},
        extract_vendor_intelligence_fn=lambda pages: VendorIntelligence(vendor_name="ExampleCorp", website="https://example.com", confidence="medium"),
        extract_vendor_intelligence_llm_fn=lambda pages: None,
        merge_vendor_intelligence_fn=lambda deterministic, llm_result: deterministic,
        build_vendor_profile_fn=lambda vendor, pages, intelligence: VendorIntelligence(
            vendor_name="ExampleCorp",
            website="https://example.com",
            confidence="high",
            include_in_directory=True,
            directory_fit="high",
            directory_category="cs_core",
        ),
        upsert_vendor_result_fn=lambda vendor, homepage, profile: upserts.append(profile.vendor_name),
    )

    assert result["ok"] is True
    assert result["action"] == "rerun-enrichment"
    assert result["vendor"]["vendor_name"] == "ExampleCorp"
    assert upserts == ["ExampleCorp"]
