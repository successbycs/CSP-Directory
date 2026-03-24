"""Lightweight admin actions for vendor quality control."""

from __future__ import annotations

import logging
from typing import Any, Callable

from services.enrichment import site_explorer
from services.enrichment import vendor_fetcher
from services.extraction import llm_extractor
from services.extraction import merge_results
from services.extraction import vendor_intel
from services.extraction import vendor_profile_builder
from services.persistence import supabase_client

logger = logging.getLogger(__name__)


def include_vendor(
    vendor_lookup: str,
    *,
    update_vendor_admin_fields_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Mark a vendor for public directory inclusion."""
    update_vendor_admin_fields_fn = update_vendor_admin_fields_fn or supabase_client.update_vendor_admin_fields
    updated = update_vendor_admin_fields_fn(vendor_lookup, include_in_directory=True)
    logger.info("Admin included vendor in directory: %s", vendor_lookup)
    return {"ok": True, "action": "include", "vendor": updated}


def exclude_vendor(
    vendor_lookup: str,
    *,
    update_vendor_admin_fields_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Remove a vendor from public directory inclusion."""
    update_vendor_admin_fields_fn = update_vendor_admin_fields_fn or supabase_client.update_vendor_admin_fields
    updated = update_vendor_admin_fields_fn(vendor_lookup, include_in_directory=False)
    logger.info("Admin excluded vendor from directory: %s", vendor_lookup)
    return {"ok": True, "action": "exclude", "vendor": updated}


def rerun_vendor_enrichment(
    vendor_lookup: str,
    *,
    find_vendor_by_lookup_fn: Callable[[str], dict[str, Any] | None] | None = None,
    fetch_vendor_homepage_fn: Callable[[dict[str, str]], dict[str, str | int]] | None = None,
    explore_vendor_site_fn: Callable[[dict[str, str | int]], dict[str, object]] | None = None,
    extract_vendor_intelligence_fn: Callable[[dict[str, object]], vendor_intel.VendorIntelligence] | None = None,
    extract_vendor_intelligence_llm_fn: Callable[[dict[str, object]], object | None] | None = None,
    merge_vendor_intelligence_fn: Callable[[vendor_intel.VendorIntelligence, object | None], vendor_intel.VendorIntelligence] | None = None,
    build_vendor_profile_fn: Callable[[dict[str, str], dict[str, object], vendor_intel.VendorIntelligence], vendor_intel.VendorIntelligence] | None = None,
    upsert_vendor_result_fn: Callable[[dict[str, str], dict[str, str | int], vendor_intel.VendorIntelligence], object] | None = None,
) -> dict[str, Any]:
    """Re-run enrichment for one vendor and persist the updated profile."""
    find_vendor_by_lookup_fn = find_vendor_by_lookup_fn or supabase_client.find_vendor_by_lookup
    fetch_vendor_homepage_fn = fetch_vendor_homepage_fn or vendor_fetcher.fetch_vendor_homepage
    explore_vendor_site_fn = explore_vendor_site_fn or site_explorer.explore_vendor_site
    extract_vendor_intelligence_fn = extract_vendor_intelligence_fn or vendor_intel.extract_vendor_intelligence
    extract_vendor_intelligence_llm_fn = (
        extract_vendor_intelligence_llm_fn or llm_extractor.extract_vendor_intelligence
    )
    merge_vendor_intelligence_fn = merge_vendor_intelligence_fn or merge_results.merge_vendor_intelligence
    build_vendor_profile_fn = build_vendor_profile_fn or vendor_profile_builder.build_vendor_profile
    upsert_vendor_result_fn = upsert_vendor_result_fn or supabase_client.upsert_vendor_result

    existing_vendor = find_vendor_by_lookup_fn(vendor_lookup)
    if not existing_vendor:
        raise LookupError(f"Vendor {vendor_lookup!r} was not found")

    vendor_candidate = {
        "vendor_name": str(existing_vendor.get("name") or existing_vendor.get("vendor_name") or ""),
        "website": str(existing_vendor.get("website") or ""),
        "source": str(existing_vendor.get("source") or "admin_rerun"),
        "raw_description": str(existing_vendor.get("raw_description") or ""),
    }
    homepage_payload = fetch_vendor_homepage_fn(vendor_candidate)
    try:
        explored_pages = explore_vendor_site_fn(homepage_payload)
    except Exception as error:
        logger.warning("Admin rerun site exploration failed for %s: %s", vendor_lookup, error)
        explored_pages = {"homepage": homepage_payload, "extra_pages": []}

    deterministic = extract_vendor_intelligence_fn(explored_pages)
    llm_result = extract_vendor_intelligence_llm_fn(explored_pages)
    intelligence = merge_vendor_intelligence_fn(deterministic, llm_result)
    profile = build_vendor_profile_fn(vendor_candidate, explored_pages, intelligence)
    upsert_vendor_result_fn(vendor_candidate, homepage_payload, profile)
    logger.info("Admin reran enrichment for vendor: %s", vendor_lookup)
    return {
        "ok": True,
        "action": "rerun-enrichment",
        "vendor": {
            "vendor_name": profile.vendor_name,
            "website": profile.website,
            "include_in_directory": profile.include_in_directory,
            "directory_fit": profile.directory_fit,
            "directory_category": profile.directory_category,
        },
    }
