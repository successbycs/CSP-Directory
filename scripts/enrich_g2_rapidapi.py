"""
G2 enrichment via n8n webhook (csp-g2-enrichment).

Architectural principle: all enrichment API calls go through n8n workflows.
This script is a batch orchestrator — it queries Supabase for vendors and
fires the n8n G2 webhook once per vendor.

Usage:
    python3 scripts/enrich_g2_rapidapi.py [--dry-run] [--limit N] [--vendor NAME]

Requires:
    N8N_G2_ENRICHMENT_WEBHOOK — n8n webhook URL for csp-g2-enrichment workflow
    RAPIDAPI_KEY               — passed to n8n, which calls G2 RapidAPI
    ADMIN_BASE_URL             — admin API base URL (default: http://127.0.0.1:8787)
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

import requests
from services.persistence import supabase_client


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print vendors without calling webhook")
    parser.add_argument("--limit", type=int, default=0, help="Max vendors to process (0=all)")
    parser.add_argument("--vendor", help="Run for a single vendor name (partial match)")
    args = parser.parse_args()

    webhook_url = os.environ.get("N8N_G2_ENRICHMENT_WEBHOOK", "").strip()
    if not webhook_url and not args.dry_run:
        print("ERROR: N8N_G2_ENRICHMENT_WEBHOOK not set in .env")
        sys.exit(1)

    rapidapi_key = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not rapidapi_key and not args.dry_run:
        print("ERROR: RAPIDAPI_KEY not set in .env")
        sys.exit(1)

    admin_url = os.environ.get("ADMIN_BASE_URL", "http://127.0.0.1:8787").strip()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    client = supabase_client.get_supabase_client()

    if args.vendor:
        result = client.table("cs_vendors").select("name, website").ilike("name", f"%{args.vendor}%").limit(5).execute()
    else:
        result = client.table("cs_vendors").select("name, website").eq("include_in_directory", True).execute()

    vendors = result.data
    if args.limit:
        vendors = vendors[: args.limit]

    print(f"Processing {len(vendors)} vendors {'(dry run)' if args.dry_run else f'via {webhook_url}'}")

    hits, misses, errors = 0, 0, 0
    results = []

    for i, v in enumerate(vendors, 1):
        name = v["name"]
        website = v.get("website") or ""
        print(f"[{i}/{len(vendors)}] {name}")

        if args.dry_run:
            print(f"    dry-run: would POST {name} / {website} to n8n")
            results.append({"vendor": name, "website": website, "dry_run": True})
            continue

        try:
            resp = requests.post(
                webhook_url,
                json={
                    "vendors": [{"vendor_name": name, "website": website}],
                    "rapidapi_key": rapidapi_key,
                    "supabase_url": supabase_url,
                    "supabase_key": supabase_key,
                    "admin_url": admin_url,
                },
                timeout=60,
            )
            data = resp.json() if resp.content else {}
            if data.get("ok"):
                hits += 1
                print(f"    ✓ rating={data.get('g2_rating')} reviews={data.get('g2_review_count')}")
            else:
                misses += 1
                print(f"    ✗ miss: {data.get('reason') or data.get('miss_reason', 'no_match')}")
            results.append({"vendor": name, **data})
        except Exception as e:
            errors += 1
            print(f"    ✗ error: {e}")
            results.append({"vendor": name, "error": str(e)})

        time.sleep(0.5)

    print(f"\nDone. Hits: {hits}, Misses: {misses}, Errors: {errors}, Total: {len(vendors)}")

    out = PROJECT_ROOT / "runs" / "proofs" / "M72_g2_rapidapi_enrichment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"hits": hits, "misses": misses, "errors": errors, "total": len(vendors), "results": results}, indent=2))
    print(f"Proof written to {out}")


if __name__ == "__main__":
    main()
