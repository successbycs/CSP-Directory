"""
Batch site crawl — calls services.ops.run_crawl for each vendor.

All crawl logic lives in services/ops/run_crawl.py. This script is a
thin orchestrator that loops vendors and invokes the shared module.

Usage:
    python scripts/enrich_site_crawl.py [--limit N] [--vendor WEBSITE] [--tier 1|2|3]
"""
from __future__ import annotations
import argparse, subprocess, sys, time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.persistence import supabase_client

PYTHON = sys.executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--vendor", help="Filter by website substring")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], default=1)
    args = parser.parse_args()

    client = supabase_client.get_supabase_client()
    q = client.table("cs_vendors").select("name, website").eq("include_in_directory", True)
    vendors = q.execute().data

    if args.vendor:
        vendors = [v for v in vendors if args.vendor.lower() in (v.get("website") or "").lower()]
    if args.limit:
        vendors = vendors[: args.limit]

    print(f"Site crawl (Tier {args.tier}): {len(vendors)} vendors", flush=True)
    ok = failed = 0

    for i, v in enumerate(vendors, 1):
        website = v.get("website") or ""
        if not website:
            continue
        print(f"[{i}/{len(vendors)}] {v['name']}", flush=True)
        result = subprocess.run(
            [PYTHON, "-m", "services.ops.run_crawl", "--vendor", website, "--tier", str(args.tier)],
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1
        time.sleep(0.3)

    print(f"\nDone: {ok} ok, {failed} failed", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
