"""
Batch AI summary generation — thin orchestrator calling services.ops.run_ai_summary
per vendor.

All summary logic lives in services/ops/run_ai_summary.py.

Usage:
    python scripts/enrich_ai_summary.py [--limit N] [--vendor WEBSITE] [--force]
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
    parser.add_argument("--force", action="store_true", help="Regenerate existing summaries")
    args = parser.parse_args()

    client = supabase_client.get_supabase_client()
    q = client.table("cs_vendors").select("name, website")
    if args.vendor:
        q = q.ilike("website", f"%{args.vendor}%").limit(5)
    else:
        q = q.eq("include_in_directory", True)
    vendors = q.execute().data

    if args.limit:
        vendors = vendors[: args.limit]

    print(f"AI summary (GPT-4o mini): {len(vendors)} vendors", flush=True)
    ok = failed = 0

    for i, v in enumerate(vendors, 1):
        website = v.get("website") or ""
        if not website:
            continue
        print(f"[{i}/{len(vendors)}] {v['name']}", flush=True)
        cmd = [PYTHON, "-m", "services.ops.run_ai_summary", "--vendor", website]
        if args.force:
            cmd.append("--force")
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            ok += 1
        else:
            failed += 1
        time.sleep(1.0)

    print(f"\nDone: {ok} ok, {failed} failed", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
