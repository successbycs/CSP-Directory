"""
Batch LLM extraction — reads vendor_pages from Supabase, embeds with
nomic-embed-text (Ollama), stores embeddings in vendor_page_embeddings,
then uses GPT-4o mini with RAG retrieval to extract structured fields.

This is the correct LLM extraction path per the architecture:
  vendor_pages -> embed -> vendor_page_embeddings -> RAG -> GPT-4o mini -> crawl_llm_result

Usage:
    python scripts/enrich_llm_extraction.py [--limit N] [--vendor WEBSITE] [--force]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.persistence import supabase_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--vendor", help="Single vendor website filter")
    parser.add_argument("--force", action="store_true", help="Re-extract even if crawl_llm_result exists")
    args = parser.parse_args()

    client = supabase_client.get_supabase_client()

    if args.vendor:
        result = client.table("cs_vendors").select("name, website, crawl_llm_result").ilike("website", f"%{args.vendor}%").limit(5).execute()
    else:
        result = client.table("cs_vendors").select("name, website, crawl_llm_result").eq("include_in_directory", True).execute()

    vendors = result.data
    if not args.force:
        # Skip vendors that already have LLM results
        vendors = [v for v in vendors if not v.get("crawl_llm_result")]

    if args.limit:
        vendors = vendors[: args.limit]

    print(f"LLM extraction (embed → RAG → GPT-4o mini): {len(vendors)} vendors")

    ok, skipped, errors = 0, 0, 0

    for i, v in enumerate(vendors, 1):
        name = v["name"]
        website = v.get("website") or ""
        print(f"[{i}/{len(vendors)}] {name}")

        # Check vendor_pages exists for this vendor first
        pages_check = client.table("vendor_pages").select("id").eq("vendor_website", website).limit(1).execute()
        if not pages_check.data:
            print(f"    SKIP — no vendor_pages found (run enrich_site_crawl.py first)")
            skipped += 1
            continue

        argv_backup = sys.argv
        sys.argv = ["run_llm_extraction", "--vendor", website]
        try:
            from services.ops.run_llm_extraction import main as run_extraction
            rc = run_extraction()
            if rc == 0:
                ok += 1
            else:
                errors += 1
        except Exception as e:
            print(f"    error: {e}")
            errors += 1
        finally:
            sys.argv = argv_backup

        time.sleep(0.5)

    print(f"\nDone. OK: {ok}, Skipped (no pages): {skipped}, Errors: {errors}, Total: {len(vendors)}")


if __name__ == "__main__":
    main()
