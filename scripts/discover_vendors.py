#!/usr/bin/env python3
"""Single entry-point pipeline: discover → enrich → health check → export.

Finds new vendor candidates via Google Search, enriches unenriched vendors,
runs the quality gate, and exports the public directory dataset.

Usage:
    python3 scripts/discover_vendors.py
    python3 scripts/discover_vendors.py --dry-run
    python3 scripts/discover_vendors.py --enrich-all   # re-enrich all vendors, not just unenriched
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from supabase import create_client
from services.discovery.apify_sources import fetch_google_search
from services.config.load_config import load_pipeline_config
from scripts.pipeline_health_check import run_health_check

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).resolve().parent


def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def step_discover(client, config, dry_run: bool) -> int:
    """Step 1: find new vendor candidates and insert into cs_vendors. Returns count of new vendors."""
    queries = list(config.discovery.queries)
    logger.info("Step 1/4 — Discovery: running %d queries", len(queries))

    existing = client.table("cs_vendors").select("website").execute()
    existing_websites = {r["website"] for r in existing.data if r.get("website")}
    logger.info("Existing vendors: %d", len(existing_websites))

    candidates = fetch_google_search(queries)
    logger.info("Discovery returned %d unique candidates", len(candidates))

    new_count = 0
    skip_count = 0
    for c in candidates:
        website = c.get("website", "").strip()
        if not website or website in existing_websites:
            skip_count += 1
            continue

        record = {
            "name": c.get("company_name") or website,
            "website": website,
            "source": c.get("source", "google_search"),
            "raw_description": c.get("raw_description", ""),
            "first_seen": date.today().isoformat(),
            "is_new": True,
        }

        if dry_run:
            print(f"  NEW {website} — {record['name'][:50]}")
        else:
            client.table("cs_vendors").upsert(record, on_conflict="website").execute()
            existing_websites.add(website)

        new_count += 1

    logger.info("Discovery: %d new vendors inserted, %d skipped (already exist)", new_count, skip_count)
    return new_count


def step_enrich(enrich_all: bool) -> int:
    """Step 2: enrich vendors. Returns subprocess exit code."""
    flag = [] if enrich_all else ["--unenriched-only"]
    label = "all" if enrich_all else "unenriched"
    logger.info("Step 2/4 — Enrichment: enriching %s vendors", label)
    result = subprocess.run([sys.executable, str(SCRIPTS_DIR / "enrich_vendors_deterministic.py")] + flag, check=False)
    return result.returncode


def step_health_check() -> bool:
    """Step 3: run quality gate. Returns True if all checks pass."""
    logger.info("Step 3/4 — Health check: running quality gate")
    return run_health_check()


def step_export() -> int:
    """Step 4: export directory dataset. Returns subprocess exit code."""
    logger.info("Step 4/4 — Export: regenerating directory_dataset.json")
    result = subprocess.run([sys.executable, str(SCRIPTS_DIR / "export_directory_dataset.py")], check=False)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Full pipeline: discover → enrich → health check → export")
    parser.add_argument("--dry-run", action="store_true", help="Print discoveries without writing to Supabase")
    parser.add_argument("--enrich-all", action="store_true", help="Re-enrich all vendors, not just unenriched")
    parser.add_argument("--skip-discover", action="store_true", help="Skip discovery, start from enrichment")
    args = parser.parse_args()

    config = load_pipeline_config()
    client = get_supabase()

    # Step 1: discover
    if not args.skip_discover:
        step_discover(client, config, dry_run=args.dry_run)
    else:
        logger.info("Step 1/4 — Discovery: skipped")

    if args.dry_run:
        logger.info("DRY RUN — stopping after discovery")
        return 0

    # Step 2: enrich
    step_enrich(enrich_all=args.enrich_all)

    # Step 3: health check — exit non-zero and skip export if it fails
    ok = step_health_check()
    if not ok:
        logger.error("Health check failed — export skipped. Fix violations and re-run.")
        return 1

    # Step 4: export
    step_export()

    logger.info("Pipeline complete: discover → enrich → health check → export")
    return 0


if __name__ == "__main__":
    sys.exit(main())
