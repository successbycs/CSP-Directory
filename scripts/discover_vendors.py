#!/usr/bin/env python3
"""Discovery-only script: find new vendor candidates via n8n Google Search.

Inserts new domains into cs_vendors (skips duplicates).
Run enrich_vendors_deterministic.py afterwards to fill fields.

Usage:
    python3 scripts/discover_vendors.py
    python3 scripts/discover_vendors.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from supabase import create_client
from services.discovery.apify_sources import fetch_google_search
from services.config.load_config import load_pipeline_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_pipeline_config()
    queries = list(config.discovery.queries)
    logger.info("Running discovery with %d queries", len(queries))

    # Fetch existing websites to deduplicate
    client = get_supabase()
    existing = client.table("cs_vendors").select("website").execute()
    existing_websites = {r["website"] for r in existing.data if r.get("website")}
    logger.info("Existing vendors: %d", len(existing_websites))

    # Run Google Search discovery
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

        if args.dry_run:
            print(f"  NEW {website} — {record['name'][:50]}")
        else:
            client.table("cs_vendors").upsert(record, on_conflict="website").execute()
            existing_websites.add(website)

        new_count += 1

    logger.info(
        "Done: %d new vendors inserted, %d skipped (already exist)",
        new_count, skip_count
    )
    if args.dry_run:
        logger.info("DRY RUN — nothing written")
        return

    # Auto-enrich newly discovered vendors immediately after discovery
    if new_count > 0:
        import subprocess, sys
        scripts_dir = Path(__file__).resolve().parent

        logger.info("Auto-enriching %d new vendors (--unenriched-only)...", new_count)
        enrich_script = scripts_dir / "enrich_vendors_deterministic.py"
        subprocess.run([sys.executable, str(enrich_script), "--unenriched-only"], check=False)

        logger.info("Re-exporting directory dataset...")
        export_script = scripts_dir / "export_directory_dataset.py"
        subprocess.run([sys.executable, str(export_script)], check=False)
        logger.info("Pipeline complete: discover → enrich → export")


if __name__ == "__main__":
    main()
