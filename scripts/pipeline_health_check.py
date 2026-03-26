#!/usr/bin/env python3
"""Pipeline health check: post-cycle quality gate.

Checks data quality conditions against cs_vendors and exits 0 (all pass) or 1 (violations found).
Runs automatically as the final step of the discover → enrich → export pipeline.

Usage:
    python3 scripts/pipeline_health_check.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.config.load_config import load_pipeline_config
from services.persistence import supabase_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def check_junk_domain_violations(
    vendor_rows: list[dict],
    junk_denylist: tuple[str, ...],
) -> list[str]:
    """Return websites that match any junk domain or subdomain thereof."""
    violations = []
    for row in vendor_rows:
        website = row.get("website") or ""
        domain = _extract_domain(website)
        if domain and _is_junk_domain(domain, junk_denylist):
            violations.append(website)
    return violations


def check_lifecycle_stage_violations(vendor_rows: list[dict]) -> list[str]:
    """Return websites where include_in_directory=True but lifecycle_stages is empty."""
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and not row.get("lifecycle_stages")
    ]


def check_missing_category_violations(vendor_rows: list[dict]) -> list[str]:
    """Return websites where include_in_directory=True but directory_category is null/empty."""
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and not row.get("directory_category")
    ]


def check_other_category_violations(vendor_rows: list[dict]) -> list[str]:
    """Return websites where include_in_directory=True and directory_category='other'."""
    return [
        row["website"]
        for row in vendor_rows
        if row.get("include_in_directory") is True and row.get("directory_category") == "other"
    ]


def run_health_check(vendor_rows: list[dict] | None = None) -> bool:
    """Run all quality gate checks. Returns True if all pass, False if any fail.

    If vendor_rows is not supplied, fetches from Supabase.
    """
    config = load_pipeline_config()

    if vendor_rows is None:
        client = supabase_client.get_supabase_client()
        response = client.table("cs_vendors").select(
            "website,include_in_directory,lifecycle_stages,directory_category"
        ).execute()
        vendor_rows = response.data or []

    violations: list[str] = []

    junk = check_junk_domain_violations(vendor_rows, config.discovery.junk_domain_denylist)
    if junk:
        violations.append(f"Junk domain violations ({len(junk)}): {junk[:5]}")

    lifecycle = check_lifecycle_stage_violations(vendor_rows)
    if lifecycle:
        violations.append(f"Missing lifecycle_stages violations ({len(lifecycle)}): {lifecycle[:5]}")

    category = check_missing_category_violations(vendor_rows)
    if category:
        violations.append(f"Missing directory_category violations ({len(category)}): {category[:5]}")

    other = check_other_category_violations(vendor_rows)
    if other:
        violations.append(f"directory_category=other violations ({len(other)}): {other[:5]}")

    if violations:
        for v in violations:
            logger.error("VIOLATION: %s", v)
        return False

    logger.info("All health checks passed (%d vendors checked)", len(vendor_rows))
    return True


def _extract_domain(website: str) -> str:
    if website.startswith("http"):
        return urlparse(website).netloc.lower()
    return website.lower()


def _is_junk_domain(domain: str, denylist: tuple[str, ...]) -> bool:
    return domain in denylist or any(domain.endswith(f".{blocked}") for blocked in denylist)


def main() -> None:
    ok = run_health_check()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
