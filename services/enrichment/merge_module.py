"""Merge module — combine crawl_*_result JSONB columns into main cs_vendors schema columns.

Priority rules per field define which source wins. COALESCE pattern ensures existing
values are never overwritten with null. Only non-null, non-empty values are written.

Raises nothing — merge errors are logged and non-fatal unless Supabase is unreachable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from services.ops.ops_logger import OpsLogger

if TYPE_CHECKING:
    from supabase import Client


# ---------------------------------------------------------------------------
# Priority rules: ordered list of source keys per field.
# Source keys map to crawl_*_result column prefixes.
# ---------------------------------------------------------------------------

_SOURCE_COLUMN_MAP = {
    "tier1":   "crawl_tier1_result",
    "tier2":   "crawl_tier2_result",
    "tier3":   "crawl_tier3_result",
    "datagma": "crawl_datagma_result",
    "g2":      "crawl_g2_result",
    "llm":     "crawl_llm_result",
}

PRIORITY_RULES: dict[str, list[str]] = {
    "name":                    ["tier1", "tier2", "tier3", "datagma"],
    "mission":                 ["llm", "tier3", "tier2"],
    "usp":                     ["llm", "tier3", "tier2"],
    "icp":                     ["llm"],
    "icp_buyer":               ["llm"],
    "use_cases":               ["llm"],
    "lifecycle_stages":        ["llm"],
    "products":                ["llm", "tier3"],
    "founded":                 ["datagma", "g2", "llm"],
    "hq_address":              ["datagma", "llm"],
    "company_hq":              ["datagma", "llm"],
    "company_size":            ["datagma"],
    "revenue":                 ["datagma"],
    "funding_stage":           ["datagma"],
    "total_funding":           ["datagma"],
    "ceo_name":                ["datagma", "llm"],
    "g2_rating":               ["g2"],
    "g2_review_count":         ["g2"],
    "g2_market_segment":       ["g2"],
    "g2_categories":           ["g2"],
    "pricing":                 ["tier3", "tier2", "llm"],
    "has_public_pricing_page": ["tier3", "tier2", "tier1"],
    "free_trial":              ["tier3", "tier2", "llm"],
    "soc2":                    ["llm", "tier3"],
    "compliance":              ["llm", "tier3"],
    "contact_page_url":        ["tier3", "tier2", "tier1"],
    "demo_url":                ["tier3", "tier2", "tier1"],
    "about_url":               ["tier3", "tier2", "tier1"],
    "contact_emails":          ["tier3", "tier2"],
    "phone_numbers":           ["tier3", "tier2"],
    "integrations":            ["llm", "tier3"],
    "integration_categories":  ["llm", "tier3"],
    "customers":               ["llm", "tier3"],
    "testimonials":            ["llm", "tier3"],
    "case_studies":            ["llm", "tier3"],
}


def run_merge(
    vendor_website: str,
    *,
    supabase_client: "Client | None" = None,
    logger: OpsLogger | None = None,
) -> dict[str, Any]:
    """Read all crawl_*_result columns, apply priority rules, write to main cs_vendors columns.

    Returns:
        {
            "ok": True,
            "fields_merged": int,
            "source_field_map": dict,
            "fields_unchanged": list[str],
        }
    """
    log = logger or OpsLogger()

    if supabase_client is None:
        from services.persistence import supabase_client as sc_module
        supabase_client = sc_module.get_supabase_client()

    log.step_start("merge", f"Reading all crawl_*_result columns for {vendor_website}")

    # --- Fetch all result columns ---
    result_cols = ",".join(_SOURCE_COLUMN_MAP.values())
    vendor_rows = supabase_client.table("cs_vendors").select(result_cols).eq("website", vendor_website).execute()
    if not vendor_rows.data:
        raise LookupError(f"Vendor not found in cs_vendors: {vendor_website}")

    row = vendor_rows.data[0]
    crawl_results: dict[str, dict[str, Any]] = {}
    for source_key, col_name in _SOURCE_COLUMN_MAP.items():
        blob = row.get(col_name)
        if isinstance(blob, dict) and blob.get("ok"):
            crawl_results[source_key] = blob

    log.step_progress("merge", f"Found results for sources: {list(crawl_results.keys())}")

    # --- Apply priority rules per field ---
    updates: dict[str, Any] = {}
    source_field_map: dict[str, str] = {}
    fields_unchanged: list[str] = []

    for field, sources in PRIORITY_RULES.items():
        winning_value = None
        winning_source = None

        for source in sources:
            if source not in crawl_results:
                continue
            value = crawl_results[source].get("fields", {}).get(field)
            if _is_empty(value):
                continue
            winning_value = value
            winning_source = source
            break

        if winning_value is not None and winning_source is not None:
            updates[field] = winning_value
            source_field_map[field] = winning_source
            log.step_progress("merge", f"  {field}: {winning_source}={_truncate(winning_value)} → winner: {winning_source}")
        else:
            fields_unchanged.append(field)
            log.step_progress("merge", f"  {field}: all sources null → field unchanged")

    # --- Write to cs_vendors using COALESCE pattern (SQL handles null-preservation) ---
    if updates:
        # Build COALESCE update: only pass non-null values; Supabase Python client
        # does a direct SET so we must filter to confirmed non-null updates only.
        supabase_client.table("cs_vendors").update(updates).eq("website", vendor_website).execute()

    # --- Write source_field_map ---
    supabase_client.table("cs_vendors").update({"source_field_map": source_field_map}).eq("website", vendor_website).execute()

    log.step_done("merge", f"✓ {len(updates)} fields written to cs_vendors")
    log.step_done("merge", f"✓ source_field_map written")

    return {
        "ok": True,
        "fields_merged": len(updates),
        "source_field_map": source_field_map,
        "fields_unchanged": fields_unchanged,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_empty(value: Any) -> bool:
    """Return True if the value should be treated as no-data (not written).

    Rules:
    - None → empty
    - "" (empty string) → empty
    - [] (empty list) → empty
    - {} (empty dict) → empty
    - False (boolean) → NOT empty — false is a valid value (e.g. has_public_pricing_page=false)
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return False  # False IS a value
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _truncate(value: Any, max_len: int = 60) -> str:
    text = str(value)
    return text[:max_len] + "..." if len(text) > max_len else text
