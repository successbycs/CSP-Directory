"""Beginner-friendly MVP pipeline orchestration."""

from __future__ import annotations

from services.discovery import web_search
from services.enrichment import site_explorer
from services.enrichment import vendor_fetcher
from services.extraction import llm_extractor
from services.extraction import merge_results
from services.extraction import vendor_intel
from services.extraction import vendor_profile_builder
from services.export import google_sheets
from services.persistence import supabase_client
from services.pipeline import orchestrator


def run_mvp_pipeline(query: str | list[str] | None = None) -> list[dict[str, str]]:
    """Run the MVP vendor intelligence pipeline for one or more search queries."""
    vendor_exists_fn = None
    upsert_vendor_result_fn = None

    if supabase_client.is_configured():
        if supabase_client.supports_export_ready_vendor_profiles():
            vendor_exists_fn = supabase_client.vendor_exists
        upsert_vendor_result_fn = supabase_client.upsert_vendor_result

    return orchestrator.run_mvp_pipeline(
        query,
        search_web_candidates_fn=web_search.search_web_candidates,
        fetch_vendor_homepage_fn=vendor_fetcher.fetch_vendor_homepage,
        explore_vendor_site_fn=site_explorer.explore_vendor_site,
        extract_vendor_intelligence_fn=vendor_intel.extract_vendor_intelligence,
        extract_vendor_intelligence_llm_fn=llm_extractor.extract_vendor_intelligence,
        merge_vendor_intelligence_fn=merge_results.merge_vendor_intelligence,
        build_vendor_profile_fn=vendor_profile_builder.build_vendor_profile,
        vendor_intelligence_to_sheet_row_fn=google_sheets.vendor_intelligence_to_sheet_row,
        vendor_exists_fn=vendor_exists_fn,
        upsert_vendor_result_fn=upsert_vendor_result_fn,
    )
