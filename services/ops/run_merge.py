"""
M76 Ops Workbench — Step 6: Clean Merge.

Reads all crawl_*_result JSONB columns for a vendor and promotes values to the
main cs_vendors schema columns using priority rules:
  LLM > Datagma > G2 > LinkedIn > existing non-null

Never overwrites a main-schema field that already has a value with null.
Writes a source_field_map JSONB column recording which source won for each field.

Usage (via pipeline_control):
    python -m services.ops.run_merge --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.ops.ops_logger import OpsLogger

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

log = OpsLogger(milestone="M76")

# Priority: later sources override earlier ones (highest priority last)
_SOURCE_PRIORITY = ["g2_rapidapi", "linkedin", "datagma", "llm_gpt4o"]

# Mapping: crawl_result field → cs_vendors column, priority tuple
_FIELD_MAP: dict[str, list[tuple[str, str]]] = {
    # (result_source, result_field): [(cs_vendors_column, source_label), ...]
    "mission":          [("crawl_llm_result", "fields.mission")],
    "usp":              [("crawl_llm_result", "fields.usp")],
    "value_proposition": [("crawl_llm_result", "fields.value_proposition")],
    "how_it_works":     [("crawl_llm_result", "fields.how_it_works")],
    "key_features":     [("crawl_llm_result", "fields.key_features")],
    "workflows":        [("crawl_llm_result", "fields.workflows")],
    "icp":              [("crawl_llm_result", "fields.icp")],
    "icp_buyer":        [("crawl_llm_result", "fields.icp_buyer")],
    "outcomes":         [("crawl_llm_result", "fields.outcomes")],
    "customers":        [("crawl_llm_result", "fields.customers")],
    "metrics":          [("crawl_llm_result", "fields.metrics")],
    "pricing":          [("crawl_llm_result", "fields.pricing")],
    "free_trial":       [("crawl_llm_result", "fields.free_trial")],
    "lifecycle_stages": [("crawl_llm_result", "fields.lifecycle_stages")],
    "integrations":     [("crawl_llm_result", "fields.integrations")],
    # Firmographic — from datagma
    "founded":          [("crawl_datagma_result", "founded"), ("crawl_g2_result", None)],
    "hq_address":       [("crawl_datagma_result", "hq_address")],
    "company_size":     [("crawl_datagma_result", "company_size")],
    "funding_stage":    [("crawl_datagma_result", "funding_stage")],
    "total_funding":    [("crawl_datagma_result", "total_funding")],
    "ceo_name":         [("crawl_datagma_result", "ceo_name")],
    "revenue":          [("crawl_datagma_result", "revenue")],
    # G2 data
    "g2_url":           [("crawl_g2_result", "g2_url")],
    "g2_rating":        [("crawl_g2_result", "g2_rating")],
    "g2_review_count":  [("crawl_g2_result", "g2_review_count")],
    "g2_categories":    [("crawl_g2_result", "g2_categories")],
}


def _get_nested(obj: dict | None, path: str | None):
    """Traverse dot-separated path in dict. Returns None if not found."""
    if obj is None or path is None:
        return None
    parts = path.split(".")
    cur = obj
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _load_vendor(website: str) -> dict | None:
    cols = ",".join([
        "website", "mission", "usp", "value_proposition", "how_it_works", "key_features",
        "workflows", "icp", "icp_buyer", "outcomes", "customers", "metrics", "pricing",
        "free_trial", "lifecycle_stages", "integrations", "founded", "hq_address",
        "company_size", "funding_stage", "total_funding", "ceo_name", "revenue",
        "g2_url", "g2_rating", "g2_review_count", "g2_categories",
        "crawl_llm_result", "crawl_datagma_result", "crawl_g2_result",
        "crawl_tier1_result", "crawl_tier2_result", "crawl_tier3_result",
        "source_field_map",
    ])
    url = (
        f"{SUPABASE_URL}/rest/v1/cs_vendors"
        f"?website=eq.{urllib.parse.quote(website, safe='')}"
        f"&select={cols}&limit=1"
    )
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read())
        return rows[0] if rows else None


def _sb_patch(website: str, fields: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.parse.quote(website, safe='')}"
    data = json.dumps(fields).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def merge_vendor(vendor: dict) -> tuple[dict, dict]:
    """Return (updates_to_write, source_field_map)."""
    updates: dict = {}
    source_map: dict = {}

    for target_col, sources in _FIELD_MAP.items():
        existing = vendor.get(target_col)
        for result_col, field_path in sources:
            result_blob = vendor.get(result_col)
            if not isinstance(result_blob, dict):
                continue
            value = _get_nested(result_blob, field_path)
            if value is None or value == "" or value == []:
                continue
            # Only write if no existing value
            if existing is None or existing == "" or existing == []:
                updates[target_col] = value
                source_map[target_col] = result_col
                existing = value  # stop at first match

    return updates, source_map


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", required=True)
    args = parser.parse_args()

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website

    if not SUPABASE_KEY:
        log.step_error("merge", "SUPABASE_KEY not set")
        return 1

    log.step_start("merge", f"Loading vendor record for {vendor_website}")
    vendor = _load_vendor(vendor_website)
    if not vendor:
        log.step_error("merge", f"Vendor not found: {vendor_website}")
        return 1

    updates, source_map = merge_vendor(vendor)
    log.step_progress("merge", f"{len(updates)} fields to write from crawl results")

    if not updates:
        log.step_done("merge", "No new values to merge — all fields already populated or no crawl results")
        return 0

    updates["source_field_map"] = {**(vendor.get("source_field_map") or {}), **source_map}
    _sb_patch(vendor_website, updates)
    log.step_done("merge", f"Merged {len(updates)-1} fields into cs_vendors for {vendor_website}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
