"""
Batch LLM enrichment — runs run_vendor_enrichment.run() for every vendor
in directory_dataset.json that hasn't yet been enriched (missing how_it_works).

Usage:
    python scripts/run_batch_enrichment.py [--limit N] [--force] [--vendor DOMAIN]

Options:
    --limit N       Only process N vendors (useful for testing)
    --force         Re-enrich vendors that already have how_it_works
    --vendor DOMAIN Only enrich one specific vendor domain
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

DATASET_PATH = PROJECT_ROOT / "docs" / "website" / "data" / "directory_dataset.json"


def main(limit: int | None = None, force: bool = False, vendor_filter: str | None = None) -> int:
    # Import here so dotenv is loaded first
    from scripts.run_vendor_enrichment import run as enrich_vendor

    dataset = json.loads(DATASET_PATH.read_text())

    # Filter candidates
    candidates = []
    for v in dataset:
        website = v.get("website", "")
        if not website:
            continue
        if vendor_filter and vendor_filter.lower() not in website.lower():
            continue
        if not force and (v.get("how_it_works") or v.get("key_features")):
            continue
        candidates.append(v)

    if limit:
        candidates = candidates[:limit]

    total = len(candidates)
    print(f"\nBatch enrichment: {total} vendors to process", flush=True)
    if total == 0:
        print("Nothing to do — all vendors already enriched. Use --force to re-run.", flush=True)
        return 0

    success = failed = 0

    for i, v in enumerate(candidates, 1):
        website = v["website"]
        name    = v.get("vendor_name", website)
        print(f"\n[{i}/{total}] {name}", flush=True)

        try:
            enriched = enrich_vendor(website, "gpt-4o")
            if not enriched:
                print(f"  WARNING: empty result for {name}", flush=True)
                failed += 1
                continue

            # Merge into dataset entry
            v.update(enriched)
            success += 1

            # Save incrementally after each vendor so progress isn't lost
            DATASET_PATH.write_text(json.dumps(dataset, indent=2))
            print(f"  Saved. ({success} done, {failed} failed so far)", flush=True)

        except Exception as e:
            print(f"  ERROR: {e}", flush=True)
            failed += 1

        # Brief pause between vendors to avoid hammering OpenAI rate limits
        if i < total:
            time.sleep(1)

    print(f"\n{'='*60}", flush=True)
    print(f"Batch complete: {success} enriched, {failed} failed out of {total}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch LLM enrichment for all vendors")
    parser.add_argument("--limit", type=int, help="Max vendors to process")
    parser.add_argument("--force", action="store_true", help="Re-enrich already-enriched vendors")
    parser.add_argument("--vendor", help="Only enrich vendors matching this domain substring")
    args = parser.parse_args()
    sys.exit(main(limit=args.limit, force=args.force, vendor_filter=args.vendor))
