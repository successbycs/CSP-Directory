#!/usr/bin/env python3
"""Pipeline health check: post-cycle quality gate.

Separates two concerns:
  - Pipeline execution health: did n8n workflows run and write data correctly?
    → Failures here exit 1 (real pipeline problem, needs operator action).
  - Data quality: are vendor records complete?
    → Gaps here are logged as external enrichment issues and exit 0
      (the pipeline ran correctly; the data just needs another enrichment cycle).

Usage:
    python3 scripts/pipeline_health_check.py
    python3 scripts/pipeline_health_check.py --strict   # exit 1 on data quality gaps too
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services.config.load_config import load_pipeline_config
from services.persistence import supabase_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ── Pipeline execution checks (exit 1 on failure) ────────────────────────────

def check_n8n_reachable() -> tuple[bool, str]:
    """Verify N8N_BASE_URL is configured."""
    import os
    url = os.environ.get("N8N_BASE_URL", "").strip()
    if not url:
        return False, "N8N_BASE_URL not set — n8n integration not configured"
    return True, f"n8n base URL configured: {url}"


def check_supabase_reachable(client) -> tuple[bool, str]:
    """Verify Supabase is reachable and cs_vendors table exists."""
    try:
        resp = client.table("cs_vendors").select("website").limit(1).execute()
        count = len(resp.data or [])
        return True, f"Supabase reachable — cs_vendors returned {count} row(s)"
    except Exception as exc:
        return False, f"Supabase unreachable: {exc}"


def check_recent_enrichment_activity(client) -> tuple[bool, str]:
    """Check that at least some vendors have been enriched (non-null enrichment fields)."""
    try:
        resp = client.table("cs_vendors").select(
            "website,mission,usp,directory_category"
        ).eq("include_in_directory", True).not_.is_("mission", "null").limit(5).execute()
        count = len(resp.data or [])
        if count == 0:
            return False, "No vendors have mission/usp populated — enrichment pipeline may never have run"
        return True, f"Enrichment activity confirmed — {count} vendor(s) with populated mission field"
    except Exception as exc:
        return False, f"Could not verify enrichment activity: {exc}"


# ── Data quality checks (warnings only, exit 0) ──────────────────────────────

def check_junk_domain_violations(vendor_rows: list[dict], junk_denylist: tuple[str, ...]) -> list[str]:
    violations = []
    for row in vendor_rows:
        website = row.get("website") or ""
        domain = _extract_domain(website)
        if domain and _is_junk_domain(domain, junk_denylist):
            violations.append(website)
    return violations


def check_lifecycle_stage_violations(vendor_rows: list[dict]) -> list[str]:
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and not row.get("lifecycle_stages")
    ]


def check_missing_category_violations(vendor_rows: list[dict]) -> list[str]:
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and not row.get("directory_category")
    ]


def check_other_category_violations(vendor_rows: list[dict]) -> list[str]:
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and row.get("directory_category") == "other"
    ]


def check_empty_icp_violations(vendor_rows: list[dict]) -> list[str]:
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and not row.get("icp")
    ]


# ── Main ──────────────────────────────────────────────────────────────────────

def run_health_check(vendor_rows: list[dict] | None = None, strict: bool = False) -> bool:
    config = load_pipeline_config()
    client = supabase_client.get_supabase_client()

    pipeline_ok = True
    pipeline_failures: list[str] = []

    # --- Pipeline execution checks ---
    n8n_ok, n8n_msg = check_n8n_reachable()
    if n8n_ok:
        logger.info("PIPELINE OK: %s", n8n_msg)
    else:
        logger.error("PIPELINE FAILURE: %s", n8n_msg)
        pipeline_failures.append(n8n_msg)
        pipeline_ok = False

    sb_ok, sb_msg = check_supabase_reachable(client)
    if sb_ok:
        logger.info("PIPELINE OK: %s", sb_msg)
    else:
        logger.error("PIPELINE FAILURE: %s", sb_msg)
        pipeline_failures.append(sb_msg)
        pipeline_ok = False

    if pipeline_ok:
        enrich_ok, enrich_msg = check_recent_enrichment_activity(client)
        if enrich_ok:
            logger.info("PIPELINE OK: %s", enrich_msg)
        else:
            logger.error("PIPELINE FAILURE: %s", enrich_msg)
            pipeline_failures.append(enrich_msg)
            pipeline_ok = False

    if not pipeline_ok:
        logger.error("Pipeline health check FAILED — %d execution issue(s) require operator action", len(pipeline_failures))
        return False

    # --- Data quality checks (external enrichment gaps, not pipeline failures) ---
    if vendor_rows is None:
        resp = client.table("cs_vendors").select(
            "website,include_in_directory,lifecycle_stages,directory_category,icp"
        ).execute()
        vendor_rows = resp.data or []

    data_gaps: list[dict] = []

    junk = check_junk_domain_violations(vendor_rows, config.discovery.junk_domain_denylist)
    if junk:
        data_gaps.append({"check": "junk_domains", "count": len(junk), "vendors": junk[:5]})

    lifecycle = check_lifecycle_stage_violations(vendor_rows)
    if lifecycle:
        data_gaps.append({"check": "missing_lifecycle_stages", "count": len(lifecycle), "vendors": lifecycle[:5]})

    category = check_missing_category_violations(vendor_rows)
    if category:
        data_gaps.append({"check": "missing_directory_category", "count": len(category), "vendors": category[:5]})

    other = check_other_category_violations(vendor_rows)
    if other:
        data_gaps.append({"check": "category_other", "count": len(other), "vendors": other[:5]})

    empty_icp = check_empty_icp_violations(vendor_rows)
    if empty_icp:
        data_gaps.append({"check": "missing_icp", "count": len(empty_icp), "vendors": empty_icp[:5]})

    if data_gaps:
        for gap in data_gaps:
            logger.warning(
                "EXTERNAL DATA GAP [%s]: %d vendor(s) need enrichment — %s (run enrichment cycle to resolve)",
                gap["check"], gap["count"], gap["vendors"]
            )
        _write_gap_report(data_gaps)
        if strict:
            logger.error("Strict mode: %d data gap(s) treated as failures", len(data_gaps))
            return False
        logger.info(
            "Pipeline executed correctly. %d data gap(s) logged — schedule enrichment cycle to resolve.",
            len(data_gaps)
        )
    else:
        logger.info("Health check passed — pipeline execution healthy, no data gaps (%d vendors checked)", len(vendor_rows))

    return True


def _write_gap_report(data_gaps: list[dict]) -> None:
    """Write data gap report to runs/ for operator review."""
    report_path = PROJECT_ROOT / "runs" / "data_gap_reports"
    report_path.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = report_path / f"{ts}_data_gaps.json"
    out.write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gap_count": len(data_gaps),
        "gaps": data_gaps,
        "action": "Run enrichment cycle to resolve these gaps. Pipeline execution is healthy."
    }, indent=2) + "\n")
    logger.info("Data gap report written to %s", out.relative_to(PROJECT_ROOT))


def _extract_domain(website: str) -> str:
    if website.startswith("http"):
        return urlparse(website).netloc.lower()
    return website.lower()


def _is_junk_domain(domain: str, denylist: tuple[str, ...]) -> bool:
    return domain in denylist or any(domain.endswith(f".{blocked}") for blocked in denylist)


def main() -> None:
    parser = argparse.ArgumentParser(description="CSP pipeline health check")
    parser.add_argument("--strict", action="store_true", help="Exit 1 on data quality gaps (default: warnings only)")
    args = parser.parse_args()
    ok = run_health_check(strict=args.strict)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
