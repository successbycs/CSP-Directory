"""
Batch AI summary generation for all include_in_directory vendors.

Calls GPT-4o mini to generate a 400-word vendor summary (what it does, who it's
for, key features, CS stack fit) and stores it in the ai_summary column.

Usage:
    python scripts/enrich_ai_summary.py [--limit N] [--vendor WEBSITE] [--force]
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
from services.ops.run_ai_summary import main as run_summary_for_vendor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--vendor", help="Single vendor website filter")
    parser.add_argument("--force", action="store_true", help="Regenerate existing summaries")
    args = parser.parse_args()

    client = supabase_client.get_supabase_client()

    if args.vendor:
        result = client.table("cs_vendors").select("name, website").ilike("website", f"%{args.vendor}%").limit(5).execute()
    else:
        result = client.table("cs_vendors").select("name, website").eq("include_in_directory", True).execute()

    vendors = result.data
    if args.limit:
        vendors = vendors[: args.limit]

    print(f"Generating AI summaries for {len(vendors)} vendors")

    ok, skipped, errors = 0, 0, 0
    for i, v in enumerate(vendors, 1):
        name = v["name"]
        website = v.get("website") or ""
        print(f"[{i}/{len(vendors)}] {name}")

        # Inject args into sys.argv for the module's argparse
        argv_backup = sys.argv
        sys.argv = ["run_ai_summary", "--vendor", website]
        if args.force:
            sys.argv.append("--force")

        try:
            rc = run_summary_for_vendor()
            if rc == 0:
                ok += 1
            else:
                errors += 1
        except Exception as e:
            print(f"    error: {e}")
            errors += 1
        finally:
            sys.argv = argv_backup

        time.sleep(1.0)  # rate limit courtesy

    print(f"\nDone. OK: {ok}, Errors: {errors}, Total: {len(vendors)}")


if __name__ == "__main__":
    main()
